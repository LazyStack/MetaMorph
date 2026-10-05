"""Nightly CSV import - not yet ported to Python 3 (still uses Python 2 except syntax)."""
import csv


def read_rows(path):
    rows = []
    try:
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
    except IOError, e:
        print("could not read %s: %s" % (path, e))
    return rows
