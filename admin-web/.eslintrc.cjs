module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 2022,
    sourceType: 'module',
  },
  extends: ['eslint:recommended', 'plugin:vue/vue3-recommended'],
  rules: {
    'vue/multi-word-component-names': 'off',
  },
  ignorePatterns: ['node_modules/', 'dist/', 'coverage/'],
}
