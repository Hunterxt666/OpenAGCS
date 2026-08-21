#include <cstdlib>
#include <iostream>

#include "../UAVcmd/fly_controller/control_command_watchdog.h"

namespace {

void Expect(bool condition, const char *description)
{
    if (!condition) {
        std::cerr << description << std::endl;
        std::exit(EXIT_FAILURE);
    }
}

} // namespace

int main()
{
    using uav_executor::IsControlSequenceFresh;
    using uav_executor::MonotonicTimeMs;
    using uav_executor::kControlSequenceTtlMs;

    Expect(kControlSequenceTtlMs == 300,
           "default control-sequence TTL must be 300 ms");
    Expect(IsControlSequenceFresh(1000, 1000),
           "a newly received sequence must be fresh");
    Expect(IsControlSequenceFresh(1299, 1000),
           "a sequence must remain fresh just before its TTL");
    Expect(!IsControlSequenceFresh(1300, 1000),
           "a sequence must expire at its TTL");
    Expect(!IsControlSequenceFresh(999, 1000),
           "a future monotonic receipt time must be rejected");
    Expect(!IsControlSequenceFresh(1000, 1000, 0),
           "a zero TTL must reject every sequence");

    const std::uint64_t before = MonotonicTimeMs();
    const std::uint64_t after = MonotonicTimeMs();
    Expect(after >= before, "the watchdog clock must be monotonic");

    std::cout << "control command watchdog tests passed" << std::endl;
    return EXIT_SUCCESS;
}
