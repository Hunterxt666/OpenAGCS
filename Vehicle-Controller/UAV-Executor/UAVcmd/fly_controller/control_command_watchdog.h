#ifndef UAV_EXECUTOR_CONTROL_COMMAND_WATCHDOG_H
#define UAV_EXECUTOR_CONTROL_COMMAND_WATCHDOG_H

#include <chrono>
#include <cstdint>

#ifndef UAV_EXECUTOR_CONTROL_SEQUENCE_TTL_MS
#define UAV_EXECUTOR_CONTROL_SEQUENCE_TTL_MS 300
#endif

namespace uav_executor {

constexpr std::uint64_t kControlSequenceTtlMs =
    UAV_EXECUTOR_CONTROL_SEQUENCE_TTL_MS;

static_assert(kControlSequenceTtlMs > 0,
              "The control-sequence TTL must be greater than zero");

inline std::uint64_t MonotonicTimeMs()
{
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count());
}

inline bool IsControlSequenceFresh(std::uint64_t nowMs,
                                   std::uint64_t receivedAtMs,
                                   std::uint64_t ttlMs =
                                       kControlSequenceTtlMs)
{
    if (nowMs < receivedAtMs) {
        return false;
    }

    return nowMs - receivedAtMs < ttlMs;
}

} // namespace uav_executor

#endif // UAV_EXECUTOR_CONTROL_COMMAND_WATCHDOG_H
