// Known verdict: AC, and the same on every run. Sums the numbers of the input.
#include <cstdio>
int main() {
    long sum = 0, x;
    while (std::scanf("%ld", &x) == 1) sum += x;
    std::printf("%ld\n", sum);
}
