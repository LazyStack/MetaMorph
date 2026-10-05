from shop.inventory import PerishableProduct, Product


def test_label():
    assert Product("A1", "Anchor", 12.5, 4).label() == "Anchor (A1) - $12.50"


def test_perishable_label_uses_parent_label():
    milk = PerishableProduct("M3", "Milk", 1.2, 7, days_left=3)
    assert milk.label() == "Milk (M3) - $1.20 [expires in 3 days]"


def test_find_and_skus(inventory):
    assert inventory.skus() == ["A1", "B2", "M3"]
    assert inventory.find("B2").name == "Bolt"
    assert inventory.find("ZZ") is None


def test_total_value_and_low_stock(inventory):
    assert inventory.total_value() == 12.5 * 4 + 0.25 * 11 + 1.2 * 7
    assert [p.sku for p in inventory.low_stock(5)] == ["A1"]
