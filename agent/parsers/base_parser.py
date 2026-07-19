from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from models.parser_models import ParserResult

class BaseParser(ABC):
    @abstractmethod
    def parse_block(self, lines: List[str], seq_num: int, event_time: datetime, file_name: str, start_line: int) -> ParserResult:
        """
        Parses a single grouped event block of text.
        Returns a ParserResult DTO containing parsed events, cassette snapshots, and warnings.
        """
        pass
