"""Plain-text stock reports."""


def format_row(name, qty):
    return "%-10s|%5d" % (name, qty)


def average_stock(inventory):
    products = [inventory.find(sku) for sku in inventory.skus()]
    avg = sum(p.qty for p in products) / len(products)
    return "Average stock: %d units" % avg


def restock_ratio(current, target):
    try:
        return current / target
    except:
        return 0.0


def report_header(title, count):
    return "== %s (%d items) ==" % (title, count)
