#include <digitalkhatt/engine.h>

extern "C" uint32_t digitalkhatt_consumer_abi() {
  return dk_engine_abi_version();
}
