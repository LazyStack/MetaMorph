from shop.reports import average_stock, format_row, report_header, restock_ratio


def test_format_row():
    assert format_row("Bolt", 11) == "Bolt      |   11"


def test_average_stock_truncates_to_whole_units(inventory):
    # (4 + 11 + 7) / 3 = 7.33 -> the report shows whole units
    assert average_stock(inventory) == "Average stock: 7 units"


def test_restock_ratio():
    assert restock_ratio(5, 10) == 0.5
    assert restock_ratio(5, 0) == 0.0


def test_report_header():
    assert report_header("Stock", 3) == "== Stock (3 items) =="
