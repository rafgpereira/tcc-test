// Known verdict: MLE. Allocates 512 MB, far above the limit of the case (throws std::bad_alloc).
#include <cstdio>
#include <cstring>
int main() {
    const unsigned long n = 512ul * 1024 * 1024;
    char* p = new char[n];
    asm volatile("" : : "r"(p) : "memory");  // keep the allocation: -O2 would elide it otherwise
    std::memset(p, 1, n);
    asm volatile("" : : "r"(p) : "memory");
    std::printf("%d\n", static_cast<int>(p[1000]));
}
