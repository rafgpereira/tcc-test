#include <bits/stdc++.h>
using namespace std;
long long labs(long long a) { return a < 0 ? (-a) : a; }
vector<int> v, v1;
int main() {
  int n;
  cin >> n;
  v.resize(n);
  v1.resize(n);
  for (int(i) = 0; (i) < (n); (i)++) {
    cin >> v[i];
    v[i]--;
  }
  for (int(i) = 0; (i) < (n); (i)++) {
    int a;
    cin >> a;
    v1[a - 1] = i;
  }
  for (int(i) = 0; (i) < (n); (i)++) {
    v[i] = v1[v[i]];
  }
  int res = n - 1;
  for (int i = 1; i < n; i++) {
    if (v[i] < v[i - 1]) {
      cout << res << endl;
      return 0;
    }
    res--;
  }
  cout << res << endl;
  return 0;
}
