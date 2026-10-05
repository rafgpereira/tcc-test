// Known verdict: AC. Needs about 150 MB of stack: it passes only with the 256 MiB run-time limit
// (the 8 MiB default would crash), which reproduces the judge's -Wl,--stack=268435456.
#include <cstdio>
static __attribute__((noinline)) long walk(long n) {
    volatile char pad[1000];
    pad[0] = 1;
    if (n == 0) return 0;
    long below = walk(n - 1);
    return below + pad[0];
}
int main() { std::printf("%ld\n", walk(150000)); }
