import React, { PureComponent } from "react";

// Uses the unsafe componentWillReceiveProps lifecycle to derive state from props.
export default class ProductList extends PureComponent {
  constructor(props) {
    super(props);
    this.state = { sorted: sortByPrice(props.products) };
  }

  componentWillReceiveProps(nextProps) {
    if (nextProps.products !== this.props.products) {
      this.setState({ sorted: sortByPrice(nextProps.products) });
    }
  }

  render() {
    return (
      <ol>
        {this.state.sorted.map((p) => (
          <li key={p.sku}>
            {p.name}: ${p.price.toFixed(2)}
          </li>
        ))}
      </ol>
    );
  }
}

function sortByPrice(products) {
  return [...products].sort((a, b) => a.price - b.price);
}
