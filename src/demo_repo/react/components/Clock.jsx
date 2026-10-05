import React from "react";

// Stateful class with lifecycle methods: needs a human to design the hooks.
export default class Clock extends React.Component {
  constructor(props) {
    super(props);
    this.state = { now: props.start || new Date() };
  }

  componentDidMount() {
    this.timer = setInterval(() => this.setState({ now: new Date() }), 1000);
  }

  componentWillUnmount() {
    clearInterval(this.timer);
  }

  render() {
    return <time>{this.state.now.toISOString()}</time>;
  }
}
