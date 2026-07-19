import os
import sys

# Ensure the agent root folder is in the Python load path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parsers.ej_parser import EJParser
from utils.logger import agent_logger

def run_parser_test():
    agent_logger.info("=== Running Phase-2 EJ Log Parser Test ===")
    
    test_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ej.log")
    if not os.path.exists(test_log_path):
        agent_logger.error(f"Test log file not found at: {test_log_path}")
        sys.exit(1)
        
    # Read test file lines
    with open(test_log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    agent_logger.info(f"Loaded {len(lines)} lines from {test_log_path}. Parsing...")
    
    parser = EJParser()
    result = parser.parse_lines(lines, file_name="test_ej.log")
    
    # 1. Print Parsed Events
    print("\n" + "=" * 80)
    print(f"PARSED EVENTS ({len(result.events)}):")
    print("=" * 80)
    for ev in result.events:
        print(f"Lines {ev.StartLineNumber}-{ev.EndLineNumber} | Seq: {ev.EventSequenceNumber:<4} | Type: {ev.EventType:<25} | Cat: {ev.EventCategory:<10} | Sev: {ev.Severity:<11} | Conf: {ev.Confidence}")
        if ev.CardNumberMasked:
            print(f"   - Card: {ev.CardNumberMasked} | Opcode: {ev.Opcode} | FuncId: {ev.FunctionId} | RespCode: {ev.ResponseCode} | Amt: {ev.Amount}")
        if ev.IsTransactionStart:
            print("   - FLAG: TransactionStart = True")
        if ev.IsTransactionEnd:
            print("   - FLAG: TransactionEnd = True")
        if ev.IsCassetteInserted:
            print("   - FLAG: CassetteInserted = True")
        if ev.IsCassetteRemoved:
            print("   - FLAG: CassetteRemoved = True")
        if ev.IsRejectBinInserted:
            print("   - FLAG: RejectBinInserted = True")
        if ev.IsRejectBinRemoved:
            print("   - FLAG: RejectBinRemoved = True")
            
    # 2. Print Cassette Snapshots
    print("\n" + "=" * 80)
    print(f"CASSETTE SNAPSHOTS ({len(result.cassette_snapshots)}):")
    print("=" * 80)
    for snap in result.cassette_snapshots:
        print(f"Lines {snap.StartLineNumber}-{snap.EndLineNumber} | Cassette: {snap.CassetteNo} | Status: {snap.CassetteStatus:<8} | Denom: {str(snap.Denomination):<4} | RemNotes: {str(snap.RemainingNotes):<5} | Amt: {str(snap.CashAmount):<8} | Op: {snap.OperationType}")
        
    # 3. Print Warnings
    print("\n" + "=" * 80)
    print(f"PARSER WARNINGS ({len(result.warnings)}):")
    print("=" * 80)
    for warn in result.warnings:
        print(f"Lines {warn.StartLineNumber}-{warn.EndLineNumber} | Seq: {warn.SequenceNumber:<4} | Msg: {warn.Message}")
        first_line = warn.RawEvent.splitlines()[0] if warn.RawEvent else ""
        print(f"   - Raw Header: {first_line}")

    # 4. Print Unknown Event Registry Summary
    print("\n" + "=" * 80)
    print(f"UNKNOWN EVENTS REGISTRY ({len(result.unknown_events_registry)} entries):")
    print("=" * 80)
    for entry in result.unknown_events_registry:
        print(f"Count: {entry.Count:<4} | FirstSeq: {entry.FirstSequence:<4} | FirstTime: {entry.FirstOccurrenceTime} | Signature: {entry.Header}")
        
    # 5. Print Statistics
    stats = result.statistics
    print("\n" + "=" * 80)
    print("PARSER STATISTICS:")
    print("=" * 80)
    print(f"Total Lines Read:      {stats.TotalLinesRead}")
    print(f"Total Blocks:          {stats.TotalBlocks}")
    print(f"Parsed Events:         {stats.ParsedEvents}")
    print(f"Cassette Snapshots:    {stats.CassetteSnapshots}")
    print(f"Cash Snapshots:        {stats.CashSnapshots}")
    print(f"Supervisor Events:     {stats.SupervisorEvents}")
    print(f"Warnings:              {stats.Warnings}")
    print(f"Unique Unknown Events: {stats.UnknownEvents}")
    print(f"Duplicates Ignored:    {stats.DuplicatesIgnored}")
    print(f"Parse Duration:        {stats.ParseDurationMs:.2f} ms")
    
    print("\n" + "=" * 80)
    agent_logger.info("Phase-2 EJ Log Parser Test execution completed.")

if __name__ == "__main__":
    run_parser_test()
