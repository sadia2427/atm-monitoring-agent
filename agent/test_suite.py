import unittest
from datetime import datetime
from parsers.ej_parser import EJParser
from models.parser_models import ParserResult

class TestEJParsingSuite(unittest.TestCase):
    def setUp(self):
        self.parser = EJParser()

    def test_sst_in_service(self):
        text = """*101*15/07/2026*10:12*
SST IN SERVICE
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        ev = res.events[0]
        self.assertEqual(ev.EventType, "SSTInService")
        self.assertEqual(ev.TerminalStatus, "InService")
        self.assertEqual(ev.Confidence, 100)
        self.assertEqual(ev.StartLineNumber, 1)
        self.assertEqual(ev.EndLineNumber, 2)

    def test_sst_out_of_service(self):
        text = """*102*15/07/2026*10:13*
SST OUT OF SERVICE
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        ev = res.events[0]
        self.assertEqual(ev.EventType, "SSTOutOfService")
        self.assertEqual(ev.TerminalStatus, "OutOfService")
        self.assertEqual(ev.Confidence, 100)

    def test_supervisor_entry(self):
        text = """*103*15/07/2026*13:07*
SUPERVISOR MODE ENTRY
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        ev = res.events[0]
        self.assertEqual(ev.EventType, "SupervisorModeEntered")
        self.assertEqual(ev.SupervisorMode, True)
        self.assertEqual(ev.Confidence, 100)

    def test_supervisor_exit(self):
        text = """*104*15/07/2026*13:08*
SUPERVISOR TASK EXITED.
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        ev = res.events[0]
        self.assertEqual(ev.EventType, "SupervisorModeExited")
        self.assertEqual(ev.SupervisorMode, False)

    def test_cassette_removed(self):
        text = """*105*15/07/2026*13:08*
TOP CASSETTE REMOVED
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        self.assertEqual(len(res.cassette_snapshots), 1)
        snap = res.cassette_snapshots[0]
        self.assertEqual(snap.CassetteNo, 1)
        self.assertEqual(snap.CassetteStatus, "Missing")
        self.assertEqual(snap.OperationType, "CassetteRemoved")

    def test_cassette_inserted(self):
        text = """*106*15/07/2026*13:11*
SECOND CASSETTE INSERTED
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        self.assertEqual(len(res.cassette_snapshots), 1)
        snap = res.cassette_snapshots[0]
        self.assertEqual(snap.CassetteNo, 2)
        self.assertEqual(snap.CassetteStatus, "Normal")
        self.assertEqual(snap.OperationType, "CassetteInserted")

    def test_cash_counts_cleared(self):
        text = """*107*15/07/2026*13:21*
CASH COUNTS CLEARED
CASH DISPENSED      
TYPE 1 ≈ 01501  TYPE 2 ≈ 01499
CASH REMAINING
TYPE 1 ≈ 00001  TYPE 2 ≈ 00000
CASH REJECTED
TYPE 1 ≈ 00001  TYPE 2 ≈ 00002
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        # 2 cassettes parsed
        self.assertEqual(len(res.cassette_snapshots), 2)
        snap1 = next(s for s in res.cassette_snapshots if s.CassetteNo == 1)
        snap2 = next(s for s in res.cassette_snapshots if s.CassetteNo == 2)
        
        self.assertEqual(snap1.DispensedNotes, 1501)
        self.assertEqual(snap1.RemainingNotes, 1)
        self.assertEqual(snap1.RejectedNotes, 1)
        self.assertEqual(snap1.CassetteStatus, "Low")
        
        self.assertEqual(snap2.DispensedNotes, 1499)
        self.assertEqual(snap2.RemainingNotes, 0)
        self.assertEqual(snap2.RejectedNotes, 2)
        self.assertEqual(snap2.CassetteStatus, "Empty")

    def test_cash_added(self):
        text = """*108*15/07/2026*13:22*
CASH ADDED
TYPE 1 ≈  1500  TYPE 2 ≈  1000
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 1)
        self.assertEqual(len(res.cassette_snapshots), 2)
        snap1 = next(s for s in res.cassette_snapshots if s.CassetteNo == 1)
        self.assertEqual(snap1.LoadedNotes, 1500)
        self.assertEqual(snap1.RemainingNotes, 1500)
        self.assertEqual(snap1.CassetteStatus, "Normal")
        self.assertEqual(snap1.OperationType, "CashAdded")

    def test_cash_total_table(self):
        text = """*109*15/07/2026*09:25*
CASH TOTAL       TYPE1 TYPE2
DENOMINATION        10    20
DISPENSED        01501 01499
REJECTED         00001 00002
REMAINING        00045 00000
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.cassette_snapshots), 2)
        snap1 = next(s for s in res.cassette_snapshots if s.CassetteNo == 1)
        snap2 = next(s for s in res.cassette_snapshots if s.CassetteNo == 2)
        
        self.assertEqual(snap1.Denomination, 10)
        self.assertEqual(snap1.DispensedNotes, 1501)
        self.assertEqual(snap1.RemainingNotes, 45)
        self.assertEqual(snap1.CashAmount, 450.0)
        self.assertEqual(snap1.CassetteStatus, "Low")
        
        self.assertEqual(snap2.Denomination, 20)
        self.assertEqual(snap2.RemainingNotes, 0)
        self.assertEqual(snap2.CassetteStatus, "Empty")

    def test_cassette_information_table(self):
        text = """*110*15/07/2026*13:17*
CASSETTE INFORMATION
POSITION   CUR   VAL   TYPE  STATUS
TOP        INR   500   1     OK
SECOND     INR   100   2     LOW
THIRD      INR   50    3     MISSING
"""
        res = self.parser.parse_text(text, "test.log")
        # 3 cassettes parsed
        self.assertEqual(len(res.cassette_snapshots), 3)
        snap1 = next(s for s in res.cassette_snapshots if s.CassetteNo == 1)
        snap2 = next(s for s in res.cassette_snapshots if s.CassetteNo == 2)
        snap3 = next(s for s in res.cassette_snapshots if s.CassetteNo == 3)
        
        self.assertEqual(snap1.CurrencyCode, "INR")
        self.assertEqual(snap1.Denomination, 500)
        self.assertEqual(snap1.CassetteStatus, "Normal")
        
        self.assertEqual(snap2.Denomination, 100)
        self.assertEqual(snap2.CassetteStatus, "Low")
        
        self.assertEqual(snap3.CassetteStatus, "Missing")

    def test_unknown_event(self):
        text = """*111*15/07/2026*13:17*
RANDOM BUTTON PRESSED
"""
        res = self.parser.parse_text(text, "test.log")
        self.assertEqual(len(res.events), 0)
        self.assertEqual(len(res.warnings), 1)
        warn = res.warnings[0]
        self.assertEqual(warn.SequenceNumber, 111)
        self.assertEqual(warn.Message, "Unknown or unhandled event block")
        
        # Check unknown registry
        self.assertEqual(len(res.unknown_events_registry), 1)
        entry = res.unknown_events_registry[0]
        self.assertEqual(entry.Header, "RANDOM BUTTON PRESSED")
        self.assertEqual(entry.Count, 1)

    def test_duplicate_event(self):
        text = """*112*15/07/2026*13:17*
SST IN SERVICE
*112*15/07/2026*13:17*
SST IN SERVICE
"""
        res = self.parser.parse_text(text, "test.log")
        # Event is parsed only once
        self.assertEqual(len(res.events), 1)
        # Statistics shows 1 duplicate ignored
        self.assertEqual(res.statistics.DuplicatesIgnored, 1)

    def test_malformed_header(self):
        # Header lacks terminal asterisk or has invalid date
        text = """*113*15/07/2026*13:17
SST IN SERVICE
"""
        res = self.parser.parse_text(text, "test.log")
        # Since header is malformed, block grouping doesn't identify it as a valid block
        self.assertEqual(len(res.events), 0)
        self.assertEqual(res.statistics.TotalBlocks, 0)

    def test_empty_block(self):
        text = """*114*15/07/2026*13:17*
"""
        res = self.parser.parse_text(text, "test.log")
        # Lacks any event text, should be recorded as unknown event warning
        self.assertEqual(len(res.events), 0)
        self.assertEqual(len(res.warnings), 1)
        self.assertEqual(res.warnings[0].SequenceNumber, 114)

if __name__ == "__main__":
    unittest.main()
