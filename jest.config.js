// Jest config for Metamorph's OWN unit tests (tests/test_*.js).
// The demo repo has its own jest.config.js, which the pipeline runs separately.
module.exports = {
  testEnvironment: "node",
  testMatch: ["<rootDir>/tests/**/test_*.js"],
};
