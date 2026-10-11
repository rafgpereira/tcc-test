// Known verdict: AC, compiled with gnu++14. A dynamic exception specification is an error since
// C++17 (gnu++20 and gnu++17 fail) but is accepted by gnu++14, so the cascade must fall back.
#include <cstdio>
void legacy() throw(int);
int main() { std::puts("ok"); }
