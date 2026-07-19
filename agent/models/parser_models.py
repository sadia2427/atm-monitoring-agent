from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass
class ATMParsedEvent:
    EventSequenceNumber: Optional[int]
    EventTime: datetime
    EventType: str
    EventCategory: str
    Severity: str
    Confidence: int
    TerminalStatus: Optional[str] = None
    Message: Optional[str] = None
    CardNumberMasked: Optional[str] = None
    ResponseCode: Optional[str] = None
    FunctionId: Optional[str] = None
    Opcode: Optional[str] = None
    Amount: Optional[float] = None
    CassetteNo: Optional[int] = None
    RemainingNotes: Optional[int] = None
    RejectNotes: Optional[int] = None
    SupervisorMode: Optional[bool] = None
    IsCashAdded: bool = False
    IsCashRemoved: bool = False
    IsCassetteInserted: bool = False
    IsCassetteRemoved: bool = False
    IsRejectBinRemoved: bool = False
    IsRejectBinInserted: bool = False
    IsCardCaptured: bool = False
    IsTransactionStart: bool = False
    IsTransactionEnd: bool = False
    RawEvent: str = ""
    SourceFileName: str = ""
    StartLineNumber: int = 0
    EndLineNumber: int = 0
    TerminalIdSnapshot: Optional[str] = None

@dataclass
class CassetteSnapshot:
    CassetteNo: int
    CassetteStatus: str
    Denomination: Optional[int] = None
    CurrencyCode: Optional[str] = None
    LoadedNotes: Optional[int] = None
    RemainingNotes: Optional[int] = None
    RejectedNotes: Optional[int] = None
    DispensedNotes: Optional[int] = None
    CashAmount: Optional[float] = None
    OperationType: str = "BalanceUpdate"
    SourceFileName: str = ""
    StartLineNumber: int = 0
    EndLineNumber: int = 0

@dataclass
class CashTotalSnapshot:
    CassetteNo: int
    Denomination: Optional[int] = None
    Dispensed: Optional[int] = None
    Rejected: Optional[int] = None
    Remaining: Optional[int] = None
    SourceFileName: str = ""
    StartLineNumber: int = 0
    EndLineNumber: int = 0

@dataclass
class SupervisorState:
    Entered: bool
    EventTime: datetime
    SourceFileName: str = ""
    StartLineNumber: int = 0
    EndLineNumber: int = 0

@dataclass
class ParserWarning:
    SequenceNumber: Optional[int]
    EventTime: Optional[datetime]
    Message: str
    RawEvent: str
    SourceFileName: str = ""
    StartLineNumber: int = 0
    EndLineNumber: int = 0

@dataclass
class UnknownEventRegistryEntry:
    Header: str
    Count: int
    FirstSequence: Optional[int]
    FirstOccurrenceTime: Optional[datetime]

@dataclass
class ParserStatistics:
    TotalLinesRead: int = 0
    TotalBlocks: int = 0
    ParsedEvents: int = 0
    CassetteSnapshots: int = 0
    CashSnapshots: int = 0
    SupervisorEvents: int = 0
    Warnings: int = 0
    UnknownEvents: int = 0
    DuplicatesIgnored: int = 0
    IgnoredBlocks: int = 0  # Added for coverage analysis
    ParseDurationMs: float = 0.0

@dataclass
class ParserResult:
    ParserVersion: str = "NCR-EJ-1.0"
    events: List[ATMParsedEvent] = field(default_factory=list)
    cassette_snapshots: List[CassetteSnapshot] = field(default_factory=list)
    warnings: List[ParserWarning] = field(default_factory=list)
    unknown_events_registry: List[UnknownEventRegistryEntry] = field(default_factory=list)
    statistics: ParserStatistics = field(default_factory=ParserStatistics)
