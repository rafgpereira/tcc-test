// Known verdict: RE. Writes through a null pointer (SIGSEGV).
int main() {
    volatile int* p = nullptr;
    *p = 1;
    return 0;
}
