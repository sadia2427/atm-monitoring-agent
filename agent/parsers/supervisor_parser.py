from datetime import datetime
from typing import List
from parsers.base_parser import BaseParser
from models.parser_models import ParserResult, ATMParsedEvent

class SupervisorParser(BaseParser):
    def parse_block(self, lines: List[str], seq_num: int, event_time: datetime, file_name: str, start_line: int) -> ParserResult:
        result = ParserResult()
        block_len = len(lines)
        end_line = start_line + block_len - 1
        
        for i, line in enumerate(lines):
            line_upper = line.upper()
            
            # 1. Supervisor Mode Entry
            if "SUPERVISOR MODE ENTRY" in line_upper or "SUPERVISOR TASK ENTERED" in line_upper:
                result.events.append(ATMParsedEvent(
                    EventSequenceNumber=seq_num,
                    EventTime=event_time,
                    EventType="SupervisorModeEntered",
                    EventCategory="Supervisor",
                    Severity="Information",
                    Confidence=100,
                    SupervisorMode=True,
                    Message="ATM entered supervisor mode",
                    SourceFileName=file_name,
                    StartLineNumber=start_line,
                    EndLineNumber=end_line
                ))
                return result
                
            # 2. Supervisor Mode Exit
            if "SUPERVISOR TASK EXITED" in line_upper:
                result.events.append(ATMParsedEvent(
                    EventSequenceNumber=seq_num,
                    EventTime=event_time,
                    EventType="SupervisorModeExited",
                    EventCategory="Supervisor",
                    Severity="Information",
                    Confidence=100,
                    SupervisorMode=False,
                    Message="ATM exited supervisor mode",
                    SourceFileName=file_name,
                    StartLineNumber=start_line,
                    EndLineNumber=end_line
                ))
                return result
                
        return result
