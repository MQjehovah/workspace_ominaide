// Host-side tests for the pure WiFi list logic in device/wifi_net.h
// Build & run:  g++ -std=c++17 -I.. test_wifi_net.cpp -o test_wifi_net && ./test_wifi_net
#include <cstdio>
#include <cstring>
#include <string>

#include "wifi_net.h"

static int g_fail = 0;

#define CHECK(cond)                                                            \
    do {                                                                       \
        if (!(cond)) {                                                         \
            std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);        \
            ++g_fail;                                                          \
        }                                                                      \
    } while (0)

static WifiCred mk(const char* s, const char* p = "") {
    WifiCred c;
    std::memset(&c, 0, sizeof(c));
    std::snprintf(c.ssid, sizeof(c.ssid), "%s", s);
    std::snprintf(c.pass, sizeof(c.pass), "%s", p);
    return c;
}

static void testPickOrdersVisibleSavedBySignal() {
    WifiCred nets[3] = {mk("home"), mk("office"), mk("cafe")};
    const char* ssids[] = {"neighbour", "cafe", "home"};
    const int   rssi[]  = {-40,         -55,    -70};
    int out[3] = {-1, -1, -1};

    int n = wifiPickBest(nets, 3, ssids, rssi, 3, out, 3);

    CHECK(n == 2);
    CHECK(out[0] == 2);   // cafe, -55
    CHECK(out[1] == 0);   // home, -70 (office invisible)
}

static void testPickReturnsZeroWhenNothingVisible() {
    WifiCred nets[2] = {mk("home"), mk("office")};
    const char* ssids[] = {"neighbour"};
    const int   rssi[]  = {-45};
    int out[2] = {-1, -1};

    int n = wifiPickBest(nets, 2, ssids, rssi, 1, out, 2);

    CHECK(n == 0);
    CHECK(out[0] == -1);
}

static void testPickRespectsOutputCapacity() {
    WifiCred nets[3] = {mk("a"), mk("b"), mk("c")};
    const char* ssids[] = {"a", "b", "c"};
    const int   rssi[]  = {-80, -60, -70};
    int out[1] = {-1};

    int n = wifiPickBest(nets, 3, ssids, rssi, 3, out, 1);

    CHECK(n == 1);
    CHECK(out[0] == 1);   // b, strongest
}

static void testPickIgnoresEmptySavedSsid() {
    WifiCred nets[2] = {mk(""), mk("home")};
    const char* ssids[] = {"home"};
    const int   rssi[]  = {-50};
    int out[2] = {-1, -1};

    int n = wifiPickBest(nets, 2, ssids, rssi, 1, out, 2);

    CHECK(n == 1);
    CHECK(out[0] == 1);
}

static void testAddAppendsNewNetwork() {
    WifiCred nets[WIFI_MAX_NETS];
    int n = 0;

    n = wifiListAdd(nets, n, "home", "pw1");
    CHECK(n == 1);
    CHECK(std::strcmp(nets[0].ssid, "home") == 0);
    CHECK(std::strcmp(nets[0].pass, "pw1") == 0);

    n = wifiListAdd(nets, n, "office", "pw2");
    CHECK(n == 2);
    CHECK(std::strcmp(nets[1].ssid, "office") == 0);
}

static void testAddUpdatesPasswordForSameSsid() {
    WifiCred nets[WIFI_MAX_NETS];
    int n = 0;
    n = wifiListAdd(nets, n, "home", "old");
    n = wifiListAdd(nets, n, "office", "pw2");
    n = wifiListAdd(nets, n, "home", "new");

    CHECK(n == 2);
    CHECK(std::strcmp(nets[0].pass, "new") == 0);
    CHECK(std::strcmp(nets[1].ssid, "office") == 0);
}

static void testAddRejectsWhenFull() {
    WifiCred nets[WIFI_MAX_NETS];
    int n = 0;
    char name[16];
    for (int i = 0; i < WIFI_MAX_NETS; ++i) {
        std::snprintf(name, sizeof(name), "net%d", i);
        n = wifiListAdd(nets, n, name, "pw");
        CHECK(n == i + 1);
    }
    CHECK(wifiListAdd(nets, n, "one_more", "pw") == -1);
    CHECK(wifiListAdd(nets, n, "net0", "changed") == WIFI_MAX_NETS);  // 已存在仍可更新
}

static void testAddRejectsInvalidSsid() {
    WifiCred nets[WIFI_MAX_NETS];
    CHECK(wifiListAdd(nets, 0, "", "pw") == -1);
    CHECK(wifiListAdd(nets, 0, nullptr, "pw") == -1);

    std::string tooLong(33, 'x');
    CHECK(wifiListAdd(nets, 0, tooLong.c_str(), "pw") == -1);

    std::string maxLen(32, 'y');
    CHECK(wifiListAdd(nets, 0, maxLen.c_str(), "pw") == 1);
}

static void testRemoveShiftsAndRejectsBadIndex() {
    WifiCred nets[WIFI_MAX_NETS];
    int n = 0;
    n = wifiListAdd(nets, n, "a", "1");
    n = wifiListAdd(nets, n, "b", "2");
    n = wifiListAdd(nets, n, "c", "3");

    n = wifiListRemove(nets, n, 1);
    CHECK(n == 2);
    CHECK(std::strcmp(nets[0].ssid, "a") == 0);
    CHECK(std::strcmp(nets[1].ssid, "c") == 0);

    CHECK(wifiListRemove(nets, n, 5) == 2);
    CHECK(wifiListRemove(nets, n, -1) == 2);
}

int main() {
    testPickOrdersVisibleSavedBySignal();
    testPickReturnsZeroWhenNothingVisible();
    testPickRespectsOutputCapacity();
    testPickIgnoresEmptySavedSsid();
    testAddAppendsNewNetwork();
    testAddUpdatesPasswordForSameSsid();
    testAddRejectsWhenFull();
    testAddRejectsInvalidSsid();
    testRemoveShiftsAndRejectsBadIndex();

    if (g_fail) {
        std::printf("%d check(s) failed\n", g_fail);
        return 1;
    }
    std::printf("all wifi_net tests passed\n");
    return 0;
}
