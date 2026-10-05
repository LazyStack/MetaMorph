import React, { Component } from "react";

// Render-only class component: a safe candidate for automatic conversion.
export default class Greeting extends Component {
  render() {
    const { name, excited } = this.props;
    return (
      <h1 className="greeting">
        Hello, {name}
        {excited ? "!" : "."}
      </h1>
    );
  }
}
