# Changelog

## [2.13.1](https://github.com/anlit75/c4o-core/compare/v2.13.0...v2.13.1) (2026-10-01)


### Fixes

* check says it builds no layout; the README is the contract, with fixes only for the newest minor ([#45](https://github.com/anlit75/c4o-core/issues/45)) ([1e450e5](https://github.com/anlit75/c4o-core/commit/1e450e5a66c70bd089b178ce4421f35297bd7d72))

## [2.13.0](https://github.com/anlit75/c4o-core/compare/v2.12.0...v2.13.0) (2026-09-30)


### Features

* the results page leads with its verdict, and reads like a product page ([#43](https://github.com/anlit75/c4o-core/issues/43)) ([6af862b](https://github.com/anlit75/c4o-core/commit/6af862b86da75875b026129357a012ff6b5804bf))

## [2.12.0](https://github.com/anlit75/c4o-core/compare/v2.11.0...v2.12.0) (2026-09-30)


### Features

* report breaks cells down by class, and site links the GDS in 3D ([#41](https://github.com/anlit75/c4o-core/issues/41)) ([94560af](https://github.com/anlit75/c4o-core/commit/94560af353e61fb52d24d4325024fe46e7eec046))

## [2.11.0](https://github.com/anlit75/c4o-core/compare/v2.10.0...v2.11.0) (2026-09-29)


### Features

* block diagrams, waveform, zoomable diagrams; report names its power corner ([#39](https://github.com/anlit75/c4o-core/issues/39)) ([48a1cc1](https://github.com/anlit75/c4o-core/commit/48a1cc1db7f24da2919a0bda2f7490a44bb57de3))

## [2.10.0](https://github.com/anlit75/c4o-core/compare/v2.9.0...v2.10.0) (2026-09-28)


### Features

* site shows signoff checks, worst setup path, area and power ([#37](https://github.com/anlit75/c4o-core/issues/37)) ([96b9de8](https://github.com/anlit75/c4o-core/commit/96b9de8f6aac664f0d7c2eec5a3b20b0d4d751e2))

## [2.9.0](https://github.com/anlit75/c4o-core/compare/v2.8.3...v2.9.0) (2026-09-28)


### Features

* site writes one page GitHub Pages can publish ([#35](https://github.com/anlit75/c4o-core/issues/35)) ([0c0532b](https://github.com/anlit75/c4o-core/commit/0c0532b7534a036f3b0c01a8427f546fea897f67))

## [2.8.3](https://github.com/anlit75/c4o-core/compare/v2.8.2...v2.8.3) (2026-09-28)


### Fixes

* read SystemVerilog in every command, not two of four ([#34](https://github.com/anlit75/c4o-core/issues/34)) ([f777b6a](https://github.com/anlit75/c4o-core/commit/f777b6ade59c64b0ff1007d0a5f73237653a685a))


### Documentation

* say that synth runs one fixed script, and where to go instead ([#31](https://github.com/anlit75/c4o-core/issues/31)) ([67d9b2d](https://github.com/anlit75/c4o-core/commit/67d9b2d37e73f2ac2eea3c033078e6993ac7ee18))
* synth maps to generic cells, so it has no area to report ([#33](https://github.com/anlit75/c4o-core/issues/33)) ([8e0fc79](https://github.com/anlit75/c4o-core/commit/8e0fc79975f610f29920eab04a63d34f87ba9d7b))

## [2.8.2](https://github.com/anlit75/c4o-core/compare/v2.8.1...v2.8.2) (2026-09-28)


### Fixes

* install the PDK where PDK_ROOT points, not always ./pdks ([#30](https://github.com/anlit75/c4o-core/issues/30)) ([a5ac5f9](https://github.com/anlit75/c4o-core/commit/a5ac5f957a727fae4dd64dc7da264e60d200ea7c))


### Documentation

* remove what expires, and say each key once ([#28](https://github.com/anlit75/c4o-core/issues/28)) ([9350e5a](https://github.com/anlit75/c4o-core/commit/9350e5a1825248598af736e8fe8dfd5fe52917f2))

## [2.8.1](https://github.com/anlit75/c4o-core/compare/v2.8.0...v2.8.1) (2026-09-26)


### Fixes

* draw one module, so schematic works on a design with a submodule ([#26](https://github.com/anlit75/c4o-core/issues/26)) ([48093c3](https://github.com/anlit75/c4o-core/commit/48093c33682a408f949e652013bec4c38fed271f))

## [2.8.0](https://github.com/anlit75/c4o-core/compare/v2.7.0...v2.8.0) (2026-09-21)


### Features

* add the toolchain a generated register block needs ([#22](https://github.com/anlit75/c4o-core/issues/22)) ([535eced](https://github.com/anlit75/c4o-core/commit/535ecedbfae29a4971cd52fb92e82495033dfc73))
* run the same cocotb tests against the netlist, not a second testbench ([#21](https://github.com/anlit75/c4o-core/issues/21)) ([d1107ef](https://github.com/anlit75/c4o-core/commit/d1107ef9acfabc6a906199e7ffd7fbf0d7102acd))


### Fixes

* let a config waive a warning that is about the generator, not the design ([#20](https://github.com/anlit75/c4o-core/issues/20)) ([4976bc4](https://github.com/anlit75/c4o-core/commit/4976bc491430bd2d82b23c28ff88bce38850f3a9))


### CI

* make merging the release, so nobody has to push a tag ([#24](https://github.com/anlit75/c4o-core/issues/24)) ([7bdc5de](https://github.com/anlit75/c4o-core/commit/7bdc5de281eff475aa8c013de588949d74b72743))
* publish the minor tag downstream repositories can pin ([#23](https://github.com/anlit75/c4o-core/issues/23)) ([7bc92e0](https://github.com/anlit75/c4o-core/commit/7bc92e05217c42a1fbf3b8b46c6383f040c1045f))


### Documentation

* fix the two lines that would send a reader into a red run ([#19](https://github.com/anlit75/c4o-core/issues/19)) ([eda0a89](https://github.com/anlit75/c4o-core/commit/eda0a89c181541e8dea5bdc633b77b4836d62b7b))
