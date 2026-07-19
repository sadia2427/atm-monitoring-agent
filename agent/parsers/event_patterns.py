import re

# 1. Main Event Header Pattern
# Matches lines like: *155*15/07/2026*08:52* or *293*15/07/2026*13:07*SUPERVISOR MODE ENTRY (allows leading whitespace)
EVENT_HEADER_PATTERN = re.compile(r'^\s*\*(?P<seq>\d+)\*(?P<date>\d{2}/\d{2}/\d{4})\*(?P<time>\d{2}:\d{2})\*(?P<extra>.*)')

# 2. Cassette Position Map
CASSETTE_POSITION_MAP = {
    "TOP": 1,
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6
}

# 3. Simple Event Log Matching Specifications
# Maps substring keywords/patterns to event properties: (EventType, EventCategory, Severity, TerminalStatus, Confidence)
# Prioritized patterns placed at the top (e.g. Transaction boundaries and Card Reader activation)
OPERATIONAL_PATTERNS = [
    (re.compile(r'^\*TRANSACTION START\*$', re.IGNORECASE | re.MULTILINE), "TransactionStart", "Transaction", "Information", None, 100),
    (re.compile(r'^TRANSACTION END$', re.IGNORECASE | re.MULTILINE), "TransactionEnd", "Transaction", "Information", None, 100),
    (re.compile(r'^\*PRIMARY CARD READER ACTIVATED\*$', re.IGNORECASE | re.MULTILINE), "CardReaderActivated", "CardReader", "Information", None, 100),
    
    (re.compile(r'^SST IN SERVICE$', re.IGNORECASE | re.MULTILINE), "SSTInService", "Status", "Information", "InService", 100),
    (re.compile(r'^SST OUT OF SERVICE$', re.IGNORECASE | re.MULTILINE), "SSTOutOfService", "Status", "Warning", "OutOfService", 100),
    (re.compile(r'^SST ON-LINE$', re.IGNORECASE | re.MULTILINE), "SSTOnline", "Status", "Information", "Online", 100),
    (re.compile(r'^SST OFF-LINE$', re.IGNORECASE | re.MULTILINE), "SSTOffline", "Status", "Warning", "Offline", 100),
    (re.compile(r'^POWER-UP/RESET$', re.IGNORECASE | re.MULTILINE), "PowerUpReset", "System", "Information", "Unknown", 100),
    (re.compile(r'^SUPERVISOR MODE ENTRY$', re.IGNORECASE | re.MULTILINE), "SupervisorModeEntered", "Supervisor", "Information", "Supervisor", 100),
    (re.compile(r'^SUPERVISOR TASK ENTERED\.$', re.IGNORECASE | re.MULTILINE), "SupervisorModeEntered", "Supervisor", "Information", "Supervisor", 100),
    (re.compile(r'^SUPERVISOR TASK EXITED\.$', re.IGNORECASE | re.MULTILINE), "SupervisorModeExited", "Supervisor", "Information", "InService", 100),
    (re.compile(r'^REJECT BIN REMOVED$', re.IGNORECASE | re.MULTILINE), "RejectBinRemoved", "RejectBin", "Warning", None, 100),
    (re.compile(r'^REJECT BIN INSERTED$', re.IGNORECASE | re.MULTILINE), "RejectBinInserted", "RejectBin", "Information", None, 100),
    (re.compile(r'^CARDS CLEARED\s*≈\s*\d+', re.IGNORECASE | re.MULTILINE), "CardsCleared", "CardReader", "Information", None, 100),
    (re.compile(r'^CARD INSERTED$', re.IGNORECASE | re.MULTILINE), "CardInserted", "CardReader", "Information", None, 80),
    (re.compile(r'^CARD TAKEN$', re.IGNORECASE | re.MULTILINE), "CardTaken", "CardReader", "Information", None, 80),
    (re.compile(r'^CUSTOMER CANCELLED$', re.IGNORECASE | re.MULTILINE), "CustomerCancelled", "Transaction", "Information", None, 80),
    (re.compile(r'^NOTES STACKED$', re.IGNORECASE | re.MULTILINE), "NotesStacked", "Cash", "Information", None, 80),
    (re.compile(r'^NOTES PRESENTED\s+[\d,]+', re.IGNORECASE | re.MULTILINE), "NotesPresented", "Cash", "Information", None, 80),
    (re.compile(r'^NOTES TAKEN$', re.IGNORECASE | re.MULTILINE), "NotesTaken", "Cash", "Information", None, 80),
    (re.compile(r'^CASH COUNTS CLEARED$', re.IGNORECASE | re.MULTILINE), "CashCountsCleared", "Cash", "Information", None, 100),
    (re.compile(r'^CASH ADDED$', re.IGNORECASE | re.MULTILINE), "CashAdded", "Cash", "Information", None, 100),
    (re.compile(r'^CASSETTE INFORMATION$', re.IGNORECASE | re.MULTILINE), "CassetteInformation", "Cassette", "Information", None, 100),
]

# 4. Silent Ignore Patterns Specifications
IGNORE_PATTERNS = [
    re.compile(r'ENTER KEY WAS PRESSED', re.IGNORECASE),
    re.compile(r'KEY PRESSED', re.IGNORECASE),
    re.compile(r'SCREEN DISPLAY', re.IGNORECASE),
    re.compile(r'DISPLAY DATA', re.IGNORECASE),
    re.compile(r'KEYBOARD INPUT', re.IGNORECASE),
    re.compile(r'^TERMINALID:\s*$', re.IGNORECASE | re.MULTILINE),
]

# 5. Specialized Cassette Insert/Remove patterns
CASSETTE_REMOVED_PATTERN = re.compile(r'^(TOP|SECOND|THIRD|FOURTH|FIFTH|SIXTH|FIRST)\s+CASSETTE\s+REMOVED', re.IGNORECASE)
CASSETTE_INSERTED_PATTERN = re.compile(r'^(TOP|SECOND|THIRD|FOURTH|FIFTH|SIXTH|FIRST)\s+CASSETTE\s+INSERTED', re.IGNORECASE)

# 6. Data Extraction Regexes (Only used when not strictly operational or when parsing cash totals)
CARD_PATTERN = re.compile(r'CARD:\s*(?P<card>\d+[\*#\d]+)', re.IGNORECASE)
CARD_NO_PATTERN = re.compile(r'CARD NO:\s*(?P<card>\d+[\*#\d]+)', re.IGNORECASE)
RESPONSE_CODE_PATTERN = re.compile(r'RESPONSE CODE:\s*(?P<resp>\w+)', re.IGNORECASE)
FUNCTION_ID_PATTERN = re.compile(r'FUNCTION ID≈(?P<func>\w+)', re.IGNORECASE)
OPCODE_PATTERN = re.compile(r'OPCODE ≈\s*(?P<opcode>\w+)', re.IGNORECASE)
AMOUNT_PATTERN = re.compile(r'AMOUNT≈(?P<amt>\d+)', re.IGNORECASE)
WITHDRAWAL_PATTERN = re.compile(r'WITHDRAWAL\s+(?P<amt>[\d\.]+)\s+BDT', re.IGNORECASE)

# 7. Cash Total Table regexes
CASH_TOTAL_HEADER_PATTERN = re.compile(r'CASH TOTAL\s+TYPE1\s+TYPE2\s+TYPE3\s+TYPE4', re.IGNORECASE)
DENOMINATION_ROW_PATTERN = re.compile(r'DENOMINATION\s+(?P<values>[\d\s]+)', re.IGNORECASE)
DISPENSED_ROW_PATTERN = re.compile(r'DISPENSED\s+(?P<values>[\d\s]+)', re.IGNORECASE)
REJECTED_ROW_PATTERN = re.compile(r'REJECTED\s+(?P<values>[\d\s]+)', re.IGNORECASE)
REMAINING_ROW_PATTERN = re.compile(r'REMAINING\s+(?P<values>[\d\s]+)', re.IGNORECASE)

# 8. Cash counts cleared/added parser regexes
CASH_COUNTS_CLEARED_CASH_DISPENSED = re.compile(r'CASH DISPENSED', re.IGNORECASE)
CASH_COUNTS_CLEARED_CASH_REMAINING = re.compile(r'CASH REMAINING', re.IGNORECASE)
CASH_COUNTS_CLEARED_CASH_REJECTED = re.compile(r'CASH REJECTED', re.IGNORECASE)
CASH_ROW_TYPE_PATTERN = re.compile(r'TYPE\s+1\s*≈\s*(?P<t1>\d+)\s+TYPE\s+2\s*≈\s*(?P<t2>\d+)(?:\s+TYPE\s+3\s*≈\s*(?P<t3>\d+)\s+TYPE\s+4\s*≈\s*(?P<t4>\d+))?', re.IGNORECASE)

# 9. Cassette Info table parser regexes
CASSETTE_INFO_ROW = re.compile(r'^(TOP|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\s+(?P<cur>\w+)\s+(?P<val>\d+)\s+(?P<type>\d+)\s+(?P<status>\w+)', re.IGNORECASE)
