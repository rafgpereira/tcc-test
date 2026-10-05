// Known verdict: AC. Prints twice the input.
#include <cstdio>
int main() {
    long n;
    if (std::scanf("%ld", &n) != 1) return 2;
    std::printf("%ld\n", 2 * n);
}
