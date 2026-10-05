import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Greeting from "../components/Greeting";
import { Badge } from "../components/Badge";
import UserCard from "../components/UserCard";
import Clock from "../components/Clock";
import ProductList from "../components/ProductList";

const html = (el) => renderToStaticMarkup(el);

describe("Greeting", () => {
  test("renders the name with punctuation", () => {
    expect(html(<Greeting name="Ada" />)).toBe('<h1 class="greeting">Hello, Ada.</h1>');
    expect(html(<Greeting name="Ada" excited />)).toBe('<h1 class="greeting">Hello, Ada!</h1>');
  });
});

describe("Badge", () => {
  test("uses defaults when color/size are missing", () => {
    expect(html(<Badge label="new" />)).toBe('<span class="badge badge-grey badge-md">new</span>');
  });
  test("explicit props win over defaults", () => {
    expect(html(<Badge label="hot" color="red" size="lg" />)).toBe('<span class="badge badge-red badge-lg">hot</span>');
  });
});

describe("UserCard", () => {
  test("renders without tags", () => {
    expect(html(<UserCard user={{ id: 1, name: "Lin" }} />)).toContain("<strong>Lin</strong><ul></ul>");
  });
  test("renders tags", () => {
    expect(html(<UserCard user={{ id: 1, name: "Lin" }} tags={["admin"]} />)).toContain("<li>admin</li>");
  });
});

describe("Clock", () => {
  test("renders the start time", () => {
    const start = new Date("2026-01-01T00:00:00Z");
    expect(html(<Clock start={start} />)).toBe("<time>2026-01-01T00:00:00.000Z</time>");
  });
});

describe("ProductList", () => {
  test("sorts products by price", () => {
    const products = [
      { sku: "b", name: "Bolt", price: 2 },
      { sku: "a", name: "Anchor", price: 1 },
    ];
    expect(html(<ProductList products={products} />)).toBe("<ol><li>Anchor: $1.00</li><li>Bolt: $2.00</li></ol>");
  });
});
