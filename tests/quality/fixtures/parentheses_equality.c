/* Deliberately bad generated-C shape: this must be rejected by Clang. */
int zen_parentheses_probe(int left, int right) {
    if ((left == right)) return 1;
    return 0;
}
