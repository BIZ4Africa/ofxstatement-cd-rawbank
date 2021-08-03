import csv
from decimal import Decimal as D

from ofxstatement import statement
from ofxstatement.parser import CsvStatementParser
from ofxstatement.plugin import Plugin
from ofxstatement.statement import generate_unique_transaction_id


class RawbankCdPlugin(Plugin):
    """Rawbank Congo Plugin
    """

    def get_parser(self, filename):
        f = open(filename, 'r', encoding=self.settings.get("charset", "UTF-8"))
        parser = RawbankCdParser(f)
        return parser

class RawbankCdParser(CsvStatementParser):

    date_format = "%d/%m/%Y"
    mappings = {
        'date': 0,
        'memo': 2,
        'amount': 3,
    }
    unique_id_set = set()
    def parse(self):
        """Main entry point for parsers

        super() implementation will call to split_records and parse_record to
        process the file.
        """
        stmt = super(RawbankCdParser, self).parse()
        statement.recalculate_balance(stmt)
        return stmt

    def split_records(self):
        """Return iterable object consisting of a line per transaction
        """
        
        reader = csv.reader(self.fin, delimiter=',')
        next(reader, None)
        return reader

    def fix_amount(self, debit, credit):

        if debit:
            amount = -1*(D(debit))
        elif credit:
            amount = D(credit)
        print("hello")
        return amount


    def parse_record(self, line):
        """Parse given transaction line and return StatementLine object
        """

        if not line[0]:
            #Continuation of previous line
            idx =len(self.statement.lines) - 1
            self.statement.lines[idx].memo = self.statement.lines[idx].memo + line[2]
            return None

        if line[0] == "Total":
            return None

        date = line[0]
        date_value = line[1]
        description = line[2]
        amount = self.fix_amount(line [3].replace(',', ''), line[4].replace(',', ''))
        line[3] = str(amount)

        if not self.statement.start_balance:
            self.statement.start_balance = D(line[5].replace(',', '')) + amount if amount > 0 else D(line[5].replace(',', '')) - amount

        stmtline = super(RawbankCdParser, self).parse_record(line)
        stmtline.id = generate_unique_transaction_id(stmtline, self.unique_id_set)
        stmtline.trntype = 'DEBIT' if stmtline.amount < 0 else 'CREDIT'

        return stmtline
