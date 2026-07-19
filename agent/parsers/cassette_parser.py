from datetime import datetime
from typing import List
from parsers.base_parser import BaseParser
from models.parser_models import ParserResult, CassetteSnapshot
from parsers.event_patterns import (
    CASSETTE_INSERTED_PATTERN,
    CASSETTE_REMOVED_PATTERN,
    CASSETTE_POSITION_MAP,
    CASSETTE_INFO_ROW,
    DENOMINATION_ROW_PATTERN,
    DISPENSED_ROW_PATTERN,
    REJECTED_ROW_PATTERN,
    REMAINING_ROW_PATTERN,
    CASH_ROW_TYPE_PATTERN,
    CASH_COUNTS_CLEARED_CASH_DISPENSED,
    CASH_COUNTS_CLEARED_CASH_REMAINING,
    CASH_COUNTS_CLEARED_CASH_REJECTED
)

class CassetteParser(BaseParser):
    def parse_block(self, lines: List[str], seq_num: int, event_time: datetime, file_name: str, start_line: int) -> ParserResult:
        result = ParserResult()
        block_len = len(lines)
        end_line = start_line + block_len - 1
        
        # 1. Check for single-line Cassette Inserted/Removed events
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Cassette Removed
            m_rem = CASSETTE_REMOVED_PATTERN.match(line_stripped)
            if m_rem:
                pos = m_rem.group(1).upper()
                c_no = CASSETTE_POSITION_MAP.get(pos, 0)
                if c_no > 0:
                    result.cassette_snapshots.append(CassetteSnapshot(
                        CassetteNo=c_no,
                        CassetteStatus="Missing",
                        OperationType="CassetteRemoved",
                        SourceFileName=file_name,
                        StartLineNumber=start_line + i,
                        EndLineNumber=start_line + i
                    ))
                continue
                
            # Cassette Inserted
            m_ins = CASSETTE_INSERTED_PATTERN.match(line_stripped)
            if m_ins:
                pos = m_ins.group(1).upper()
                c_no = CASSETTE_POSITION_MAP.get(pos, 0)
                if c_no > 0:
                    result.cassette_snapshots.append(CassetteSnapshot(
                        CassetteNo=c_no,
                        CassetteStatus="Normal",
                        OperationType="CassetteInserted",
                        SourceFileName=file_name,
                        StartLineNumber=start_line + i,
                        EndLineNumber=start_line + i
                    ))
                continue

        # 2. Parse CASSETTE INFORMATION status table
        has_cassette_info = any("CASSETTE INFORMATION" in line for line in lines)
        if has_cassette_info:
            for i, line in enumerate(lines):
                m_row = CASSETTE_INFO_ROW.match(line.strip())
                if m_row:
                    pos = m_row.group(1).upper()
                    c_no = CASSETTE_POSITION_MAP.get(pos, 0)
                    if c_no > 0:
                        cur = m_row.group("cur")
                        val_str = m_row.group("val")
                        denom = int(val_str) if val_str.isdigit() else None
                        status_raw = m_row.group("status").upper()
                        
                        status = "Unknown"
                        if status_raw == "OK":
                            status = "Normal"
                        elif status_raw == "MISSING":
                            status = "Missing"
                        elif status_raw == "LOW":
                            status = "Low"
                        elif status_raw == "EMPTY":
                            status = "Empty"
                        elif status_raw == "FAULT":
                            status = "Fault"
                            
                        result.cassette_snapshots.append(CassetteSnapshot(
                            CassetteNo=c_no,
                            CassetteStatus=status,
                            Denomination=denom,
                            CurrencyCode=cur,
                            OperationType="BalanceUpdate",
                            SourceFileName=file_name,
                            StartLineNumber=start_line + i,
                            EndLineNumber=start_line + i
                        ))
            if result.cassette_snapshots:
                return result

        # 3. Parse CASH TOTAL tables
        denoms = []
        dispensed = []
        rejected = []
        remaining = []
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            m_denom = DENOMINATION_ROW_PATTERN.search(line_stripped)
            if m_denom:
                denoms = [int(x) for x in m_denom.group("values").split()]
                continue
                
            m_disp = DISPENSED_ROW_PATTERN.search(line_stripped)
            if m_disp:
                dispensed = [int(x) for x in m_disp.group("values").split()]
                continue
                
            m_rej = REJECTED_ROW_PATTERN.search(line_stripped)
            if m_rej:
                rejected = [int(x) for x in m_rej.group("values").split()]
                continue
                
            m_rem = REMAINING_ROW_PATTERN.search(line_stripped)
            if m_rem:
                remaining = [int(x) for x in m_rem.group("values").split()]
                continue
                
        if denoms or dispensed or rejected or remaining:
            num_cassettes = max(len(denoms), len(dispensed), len(rejected), len(remaining))
            for idx in range(num_cassettes):
                c_no = idx + 1
                c_denom = denoms[idx] if idx < len(denoms) else None
                c_disp = dispensed[idx] if idx < len(dispensed) else None
                c_rej = rejected[idx] if idx < len(rejected) else None
                c_rem = remaining[idx] if idx < len(remaining) else None
                
                c_status = "Normal"
                if c_rem is not None:
                    if c_rem == 0:
                        c_status = "Empty"
                    elif c_rem <= 50:
                        c_status = "Low"
                        
                c_amount = float(c_denom * c_rem) if (c_denom is not None and c_rem is not None) else None
                
                result.cassette_snapshots.append(CassetteSnapshot(
                    CassetteNo=c_no,
                    CassetteStatus=c_status,
                    Denomination=c_denom,
                    DispensedNotes=c_disp,
                    RejectedNotes=c_rej,
                    RemainingNotes=c_rem,
                    CashAmount=c_amount,
                    OperationType="BalanceUpdate",
                    SourceFileName=file_name,
                    StartLineNumber=start_line,
                    EndLineNumber=end_line
                ))
            if result.cassette_snapshots:
                return result

        # 4. Parse CASH COUNTS CLEARED / CASH ADDED events
        is_cleared = any("CASH COUNTS CLEARED" in line for line in lines)
        is_added = any("CASH ADDED" in line for line in lines)
        
        if is_cleared or is_added:
            op_type = "CashCountsCleared" if is_cleared else "CashAdded"
            section = None
            
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                
                if CASH_COUNTS_CLEARED_CASH_DISPENSED.search(line_stripped):
                    section = "dispensed"
                    continue
                elif CASH_COUNTS_CLEARED_CASH_REMAINING.search(line_stripped):
                    section = "remaining"
                    continue
                elif CASH_COUNTS_CLEARED_CASH_REJECTED.search(line_stripped):
                    section = "rejected"
                    continue
                    
                m_type_row = CASH_ROW_TYPE_PATTERN.search(line_stripped)
                if m_type_row:
                    vals = []
                    for key in ["t1", "t2", "t3", "t4"]:
                        val_str = m_type_row.group(key)
                        if val_str:
                            vals.append(int(val_str))
                            
                    for idx, val in enumerate(vals):
                        c_no = idx + 1
                        
                        snap = next((s for s in result.cassette_snapshots if s.CassetteNo == c_no), None)
                        if not snap:
                            snap = CassetteSnapshot(
                                CassetteNo=c_no,
                                CassetteStatus="Normal",
                                OperationType=op_type,
                                SourceFileName=file_name,
                                StartLineNumber=start_line,
                                EndLineNumber=end_line
                            )
                            result.cassette_snapshots.append(snap)
                            
                        if is_added:
                            snap.LoadedNotes = val
                            snap.RemainingNotes = val
                            snap.CassetteStatus = "Normal"
                        else:
                            if section == "dispensed":
                                snap.DispensedNotes = val
                            elif section == "remaining":
                                snap.RemainingNotes = val
                                if val == 0:
                                    snap.CassetteStatus = "Empty"
                                elif val <= 50:
                                    snap.CassetteStatus = "Low"
                            elif section == "rejected":
                                snap.RejectedNotes = val
                                
        return result
