// Known verdict: WA. Well behaved, but the answer is wrong (twice the input plus one).
#include <cstdio>
int main() {
    long n;
    if (std::scanf("%ld", &n) != 1) return 2;
    std::printf("%ld\n", 2 * n + 1);
}
