import os
import time
from datetime import datetime
from typing import List, Tuple, Dict
from parsers.base_parser import BaseParser
from parsers.cassette_parser import CassetteParser
from parsers.supervisor_parser import SupervisorParser
from models.parser_models import (
    ParserResult,
    ATMParsedEvent,
    ParserWarning,
    ParserStatistics,
    UnknownEventRegistryEntry
)
from parsers.event_patterns import (
    EVENT_HEADER_PATTERN,
    OPERATIONAL_PATTERNS,
    IGNORE_PATTERNS,
    CARD_PATTERN,
    CARD_NO_PATTERN,
    RESPONSE_CODE_PATTERN,
    FUNCTION_ID_PATTERN,
    OPCODE_PATTERN,
    AMOUNT_PATTERN,
    WITHDRAWAL_PATTERN
)

def parse_ncr_datetime(date_str: str, time_str: str) -> datetime:
    """Helper to parse date and time from NCR header supporting multiple formats."""
    dt_str = f"{date_str} {time_str}"
    for fmt in ["%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%y %H:%M", "%d-%m-%y %H:%M"]:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return datetime.now()

class EJParser:
    def __init__(self):
        self.cassette_parser = CassetteParser()
        self.supervisor_parser = SupervisorParser()

    def parse_text(self, text: str, file_name: str = "ej.log") -> ParserResult:
        """Helper to parse a raw string content directly."""
        lines = text.splitlines()
        return self.parse_lines(lines, file_name)

    def parse_lines(self, lines: List[str], file_name: str) -> ParserResult:
        """
        Groups EJ lines into sequential blocks by header, runs duplicate checks,
        delegates to sub-parsers, tracks performance stats, and registers unknown events.
        """
        start_time = time.perf_counter()
        consolidated = ParserResult(ParserVersion="NCR-EJ-1.0")
        
        # 1. Partition blocks
        blocks = self._group_blocks(lines)
        
        # Keep track of duplicates and ignored events
        seen_blocks = set()
        duplicates_count = 0
        ignored_count = 0
        
        # Keep track of unknown event registry
        unknown_registry: Dict[str, UnknownEventRegistryEntry] = {}
        
        for seq, dt, extra, block_lines, start_idx in blocks:
            # 1-indexed line numbers
            start_line_num = start_idx + 1
            end_line_num = start_line_num + len(block_lines) - 1
            
            # 2. Duplicate Detection
            event_key = (seq, dt)
            if event_key in seen_blocks:
                duplicates_count += 1
                continue
            seen_blocks.add(event_key)

            # Strip each line to remove leading/trailing whitespaces before pattern matching
            search_lines = [l.strip() for l in block_lines]
            search_text = extra.strip() + "\n" + "\n".join(search_lines)
            
            # 3. Silent Ignore Patterns Check
            is_ignored = False
            for pat in IGNORE_PATTERNS:
                if pat.search(search_text):
                    is_ignored = True
                    break
            if is_ignored:
                ignored_count += 1
                continue

            raw_block = "\n".join(block_lines)
            
            # Initialize parsed properties
            matched = False
            event_type = "Unknown"
            event_category = "System"
            severity = "Information"
            terminal_status = None
            message = None
            confidence = 60 # Default fallback confidence
            supervisor_mode = None

            # 4. Search operational keyword matches
            for pattern, ev_type, ev_cat, sev, term_stat, conf in OPERATIONAL_PATTERNS:
                if pattern.search(search_text):
                    event_type = ev_type
                    event_category = ev_cat
                    severity = sev
                    terminal_status = term_stat
                    confidence = conf
                    matched = True
                    break

            # 5. Extract transaction fields if relevant (and not TransactionStart)
            card_num = None
            resp_code = None
            func_id = None
            opcode = None
            amount = None

            if event_type != "TransactionStart":
                card_m = CARD_PATTERN.search(search_text) or CARD_NO_PATTERN.search(search_text)
                if card_m:
                    card_num = card_m.group("card")
                
                resp_m = RESPONSE_CODE_PATTERN.search(search_text)
                if resp_m:
                    resp_code = resp_m.group("resp")

                func_m = FUNCTION_ID_PATTERN.search(search_text)
                if func_m:
                    func_id = func_m.group("func")

                op_m = OPCODE_PATTERN.search(search_text)
                if op_m:
                    opcode = op_m.group("opcode")

                amt_m = AMOUNT_PATTERN.search(search_text) or WITHDRAWAL_PATTERN.search(search_text)
                if amt_m:
                    try:
                        amount = float(amt_m.group("amt"))
                    except ValueError:
                        pass

            # 6. Delegate to sub-parsers
            sub_res_cass = self.cassette_parser.parse_block(block_lines, seq, dt, file_name, start_line_num)
            sub_res_super = self.supervisor_parser.parse_block(block_lines, seq, dt, file_name, start_line_num)

            # Integrate sub-parser events
            if sub_res_super.events:
                # Use supervisor event if detected
                event_type = sub_res_super.events[0].EventType
                event_category = sub_res_super.events[0].EventCategory
                severity = sub_res_super.events[0].Severity
                terminal_status = sub_res_super.events[0].TerminalStatus
                confidence = sub_res_super.events[0].Confidence
                supervisor_mode = sub_res_super.events[0].SupervisorMode
                matched = True

            # If cassette status events were parsed (inserted/removed)
            if sub_res_cass.cassette_snapshots:
                consolidated.cassette_snapshots.extend(sub_res_cass.cassette_snapshots)
                # If there are cassette actions, use them to denote primary event
                for snap in sub_res_cass.cassette_snapshots:
                    if snap.OperationType in ["CassetteInserted", "CassetteRemoved", "CashAdded", "CashCountsCleared"]:
                        event_type = snap.OperationType
                        event_category = "Cassette" if "Cassette" in snap.OperationType else "Cash"
                        severity = "Warning" if snap.OperationType == "CassetteRemoved" else "Information"
                        confidence = 100
                        matched = True

            # 7. Populate primary event DTO
            if matched or event_type != "Unknown":
                if opcode:
                    opcode = opcode.strip()

                is_txn_start = "TransactionStart" in event_type or "*TRANSACTION START*" in search_text
                is_txn_end = "TransactionEnd" in event_type or "TRANSACTION END" in search_text
                is_card_cap = "CARDS CAPTURED" in search_text

                parsed_event = ATMParsedEvent(
                    EventSequenceNumber=seq,
                    EventTime=dt,
                    EventType=event_type,
                    EventCategory=event_category,
                    Severity=severity,
                    Confidence=confidence,
                    TerminalStatus=terminal_status,
                    Message=message or f"Parsed {event_type} event",
                    CardNumberMasked=card_num,
                    ResponseCode=resp_code,
                    FunctionId=func_id,
                    Opcode=opcode,
                    Amount=amount,
                    SupervisorMode=supervisor_mode,
                    IsCashAdded=(event_type == "CashAdded"),
                    IsCashRemoved=(event_type == "CashCountsCleared"),
                    IsCassetteInserted=(event_type == "CassetteInserted"),
                    IsCassetteRemoved=(event_type == "CassetteRemoved"),
                    IsRejectBinInserted=(event_type == "RejectBinInserted"),
                    IsRejectBinRemoved=(event_type == "RejectBinRemoved"),
                    IsCardCaptured=is_card_cap,
                    IsTransactionStart=is_txn_start,
                    IsTransactionEnd=is_txn_end,
                    RawEvent=raw_block,
                    SourceFileName=file_name,
                    StartLineNumber=start_line_num,
                    EndLineNumber=end_line_num
                )
                consolidated.events.append(parsed_event)
            else:
                # 8. Unknown Event Registration
                # Find the first non-empty line of the body to serve as the header signature
                body_lines_cleaned = [l.strip() for l in block_lines[1:] if l.strip()]
                unknown_header = body_lines_cleaned[0] if body_lines_cleaned else block_lines[0].strip()
                
                # Limit size of signature to prevent bloating
                if len(unknown_header) > 100:
                    unknown_header = unknown_header[:97] + "..."
                    
                if unknown_header in unknown_registry:
                    unknown_registry[unknown_header].Count += 1
                else:
                    unknown_registry[unknown_header] = UnknownEventRegistryEntry(
                        Header=unknown_header,
                        Count=1,
                        FirstSequence=seq,
                        FirstOccurrenceTime=dt
                    )
                
                # Append warning DTO
                consolidated.warnings.append(ParserWarning(
                    SequenceNumber=seq,
                    EventTime=dt,
                    Message="Unknown or unhandled event block",
                    RawEvent=raw_block,
                    SourceFileName=file_name,
                    StartLineNumber=start_line_num,
                    EndLineNumber=end_line_num
                ))

        # Compile registry entries to consolidated result
        consolidated.unknown_events_registry = list(unknown_registry.values())
        
        # 9. Compile Parser Statistics
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000.0
        
        cash_snaps = sum(
            1 for s in consolidated.cassette_snapshots 
            if s.RemainingNotes is not None or s.DispensedNotes is not None or s.RejectedNotes is not None
        )
        
        super_events = sum(
            1 for e in consolidated.events 
            if e.EventCategory == "Supervisor"
        )
        
        consolidated.statistics = ParserStatistics(
            TotalLinesRead=len(lines),
            TotalBlocks=len(blocks),
            ParsedEvents=len(consolidated.events),
            CassetteSnapshots=len(consolidated.cassette_snapshots),
            CashSnapshots=cash_snaps,
            SupervisorEvents=super_events,
            Warnings=len(consolidated.warnings),
            UnknownEvents=len(consolidated.unknown_events_registry),
            DuplicatesIgnored=duplicates_count,
            IgnoredBlocks=ignored_count,
            ParseDurationMs=duration_ms
        )

        return consolidated

    def _group_blocks(self, lines: List[str]) -> List[Tuple[int, datetime, str, List[str], int]]:
        """
        Groups lines by sequence number headers.
        Returns a list of tuples: (seq_num, datetime, extra_text, body_lines, start_line_index)
        """
        blocks = []
        current_seq = None
        current_dt = None
        current_extra = ""
        current_body = []
        current_start_idx = 0

        for idx, line in enumerate(lines):
            line_str = line.rstrip('\r\n')
            m_header = EVENT_HEADER_PATTERN.match(line_str)
            
            if m_header:
                if current_seq is not None:
                    blocks.append((current_seq, current_dt, current_extra, current_body, current_start_idx))
                
                current_seq = int(m_header.group("seq"))
                date_str = m_header.group("date")
                time_str = m_header.group("time")
                current_dt = parse_ncr_datetime(date_str, time_str)
                current_extra = m_header.group("extra")
                current_body = [line_str]
                current_start_idx = idx
            else:
                if current_seq is not None:
                    current_body.append(line_str)
                    
        if current_seq is not None:
            blocks.append((current_seq, current_dt, current_extra, current_body, current_start_idx))

        return blocks
