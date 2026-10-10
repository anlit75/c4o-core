# Changelog

## [2.25.0](https://github.com/anlit75/c4o-core/compare/v2.24.0...v2.25.0) (2026-10-10)


### Features

* render each stage of the flow and show it on the results page ([#97](https://github.com/anlit75/c4o-core/issues/97)) ([75ce308](https://github.com/anlit75/c4o-core/commit/75ce308a26bfe3e44d9ed58b5295d931bc22aa78))
* show a progress ledger for make all and make gds ([#95](https://github.com/anlit75/c4o-core/issues/95)) ([faad779](https://github.com/anlit75/c4o-core/commit/faad779f581df90025b045a56ebdadbbf8f0c08e))

## [2.24.0](https://github.com/anlit75/c4o-core/compare/v2.23.0...v2.24.0) (2026-10-08)


### Features

* add Next hints, honor NO_COLOR and name the release in log output ([#93](https://github.com/anlit75/c4o-core/issues/93)) ([4e52f4d](https://github.com/anlit75/c4o-core/commit/4e52f4dac16adeaef036c119cb5e99f279735dfa))

## [2.23.0](https://github.com/anlit75/c4o-core/compare/v2.22.3...v2.23.0) (2026-10-06)


### Features

* chart each section's history and offer its files on the results page ([#91](https://github.com/anlit75/c4o-core/issues/91)) ([f43336f](https://github.com/anlit75/c4o-core/commit/f43336f53a4102c587d1bab5ea5fc58837c40e74))

## [2.22.3](https://github.com/anlit75/c4o-core/compare/v2.22.2...v2.22.3) (2026-10-06)


### Fixes

* keep units, limit names and layout verdicts from wrapping apart ([#88](https://github.com/anlit75/c4o-core/issues/88)) ([58b4b1a](https://github.com/anlit75/c4o-core/commit/58b4b1a8d7d6625ac79436c687db9547d5d8bd7b))
* show limit violations as warnings, not failures ([#90](https://github.com/anlit75/c4o-core/issues/90)) ([24a1c1d](https://github.com/anlit75/c4o-core/commit/24a1c1d833e6f9813450bd47499ce6d73d9016fa))

## [2.22.2](https://github.com/anlit75/c4o-core/compare/v2.22.1...v2.22.2) (2026-10-06)


### Fixes

* list each regression module's tests and seeds, and fit the layout image ([#85](https://github.com/anlit75/c4o-core/issues/85)) ([5e0cd5b](https://github.com/anlit75/c4o-core/commit/5e0cd5bb28c640b9c3df666e7ba1dd1411b2706c))
* show slew, cap and fanout violations, and lint with LibreLane's flags ([#87](https://github.com/anlit75/c4o-core/issues/87)) ([ae22851](https://github.com/anlit75/c4o-core/commit/ae2285129c89405c3f2376458ee3b95ee11fcce9))

## [2.22.1](https://github.com/anlit75/c4o-core/compare/v2.22.0...v2.22.1) (2026-10-06)


### Fixes

* apply STE writing rules and show n/a for a missing value on the page ([#84](https://github.com/anlit75/c4o-core/issues/84)) ([6adcc15](https://github.com/anlit75/c4o-core/commit/6adcc15648ec2e8741b39ca2af5de980de9100d7))
* tighten the result page wording ([#82](https://github.com/anlit75/c4o-core/issues/82)) ([785f87f](https://github.com/anlit75/c4o-core/commit/785f87f1e4217c2c578943bd249a608764645b2c))

## [2.22.0](https://github.com/anlit75/c4o-core/compare/v2.21.0...v2.22.0) (2026-10-05)


### Features

* run a cocotb test list over many seeds with make regress ([#80](https://github.com/anlit75/c4o-core/issues/80)) ([2572290](https://github.com/anlit75/c4o-core/commit/25722902ecc37b4629ef81c9491cfd4e5807b6d3))

## [2.21.0](https://github.com/anlit75/c4o-core/compare/v2.20.1...v2.21.0) (2026-10-05)


### Features

* measure code coverage on Verilator and show it on the results page ([#78](https://github.com/anlit75/c4o-core/issues/78)) ([9eff22c](https://github.com/anlit75/c4o-core/commit/9eff22c158e33cbe3f0b1832c9a28ca38877c767))

## [2.20.1](https://github.com/anlit75/c4o-core/compare/v2.20.0...v2.20.1) (2026-10-05)


### Fixes

* restore the results page Summary and tidy its wording ([#76](https://github.com/anlit75/c4o-core/issues/76)) ([cfbdf51](https://github.com/anlit75/c4o-core/commit/cfbdf51abb40813d466e94b15c595c49225b8291))

## [2.20.0](https://github.com/anlit75/c4o-core/compare/v2.19.0...v2.20.0) (2026-10-04)


### Features

* show drive strength after synthesis and after routing ([#74](https://github.com/anlit75/c4o-core/issues/74)) ([de55666](https://github.com/anlit75/c4o-core/commit/de55666c97fc968c52e006fe7c802fd18ed3ef21))

## [2.19.0](https://github.com/anlit75/c4o-core/compare/v2.18.0...v2.19.0) (2026-10-04)


### Features

* show a reviewer's results page and opt-in cocotb waves ([#72](https://github.com/anlit75/c4o-core/issues/72)) ([440355d](https://github.com/anlit75/c4o-core/commit/440355da85a770f05caeba09229f02ac31655307))

## [2.18.0](https://github.com/anlit75/c4o-core/compare/v2.17.0...v2.18.0) (2026-10-04)


### Features

* gatesim runs the cocotb tests and sim is optional ([#71](https://github.com/anlit75/c4o-core/issues/71)) ([b4f6c04](https://github.com/anlit75/c4o-core/commit/b4f6c0411a5a541eee6ad0e7b9310231b0b55a95))


### CI

* run the composite actions end to end against ChipForAll ([#69](https://github.com/anlit75/c4o-core/issues/69)) ([eddddd1](https://github.com/anlit75/c4o-core/commit/eddddd101835539b4229b5f9ca7b9b7124c18a61))

## [2.17.0](https://github.com/anlit75/c4o-core/compare/v2.16.0...v2.17.0) (2026-10-04)


### Features

* the Makefile rules of a template copy ship in the image ([#67](https://github.com/anlit75/c4o-core/issues/67)) ([e7d71ad](https://github.com/anlit75/c4o-core/commit/e7d71ad4a8207a01ba7b6c7eb0940d5884d7ac1a))

## [2.16.0](https://github.com/anlit75/c4o-core/compare/v2.15.3...v2.16.0) (2026-10-04)


### Features

* composite actions that run the flow in a repository made from the template ([#66](https://github.com/anlit75/c4o-core/issues/66)) ([9a96214](https://github.com/anlit75/c4o-core/commit/9a96214c6deb81d0e64a6d5eb8c7aa0f350a4b7f))


### CI

* run on pushes to main, and skip the image build for release pull requests ([#64](https://github.com/anlit75/c4o-core/issues/64)) ([93c58f9](https://github.com/anlit75/c4o-core/commit/93c58f958f094cbd14ba932a83980575660a36ff))

## [2.15.3](https://github.com/anlit75/c4o-core/compare/v2.15.2...v2.15.3) (2026-10-03)


### Fixes

* report and site read only the steps of the run final/ describes ([#62](https://github.com/anlit75/c4o-core/issues/62)) ([c261ac5](https://github.com/anlit75/c4o-core/commit/c261ac516f0ca6bd61f6fea9220117450dd1769e))

## [2.15.2](https://github.com/anlit75/c4o-core/compare/v2.15.1...v2.15.2) (2026-10-03)


### Fixes

* site and report read the newest step of a resumed run, not the one that sorts last ([#60](https://github.com/anlit75/c4o-core/issues/60)) ([6bcc2c8](https://github.com/anlit75/c4o-core/commit/6bcc2c875eb21500ffd35675ce1db745ffba5c1b))

## [2.15.1](https://github.com/anlit75/c4o-core/compare/v2.15.0...v2.15.1) (2026-10-03)


### Fixes

* **site:** GDS frame, per-run chips, timing and schematic reworked, numbers a physical designer can trust ([#58](https://github.com/anlit75/c4o-core/issues/58)) ([6bfee36](https://github.com/anlit75/c4o-core/commit/6bfee36773bcc51c7903e914210fc1657dc10166))

## [2.15.0](https://github.com/anlit75/c4o-core/compare/v2.14.2...v2.15.0) (2026-10-01)


### Features

* **site:** a download link on every zoomable diagram ([#56](https://github.com/anlit75/c4o-core/issues/56)) ([cbcf8ad](https://github.com/anlit75/c4o-core/commit/cbcf8ad2eb9131065111a7f1407c31360de72eb6))


### Fixes

* **site:** quiet GDS button, readable dark primary, honest power bars ([#55](https://github.com/anlit75/c4o-core/issues/55)) ([aa152bf](https://github.com/anlit75/c4o-core/commit/aa152bf88644f0a0ca7ce074966d610c0a4429da))

## [2.14.2](https://github.com/anlit75/c4o-core/compare/v2.14.1...v2.14.2) (2026-10-01)


### Fixes

* **site:** polish the results page and warn on a missing `timescale ([#53](https://github.com/anlit75/c4o-core/issues/53)) ([8db41e9](https://github.com/anlit75/c4o-core/commit/8db41e9804068d9e4f2b4814dcbc75d73a6b4c14))

## [2.14.1](https://github.com/anlit75/c4o-core/compare/v2.14.0...v2.14.1) (2026-10-01)


### Fixes

* the area and cell-class figures read as what the chip is made of, not as highlighted text ([#51](https://github.com/anlit75/c4o-core/issues/51)) ([e721254](https://github.com/anlit75/c4o-core/commit/e7212541639353f167dedaf1d72efb671a6f8499))

## [2.14.0](https://github.com/anlit75/c4o-core/compare/v2.13.2...v2.14.0) (2026-10-01)


### Features

* the results page reads as a portfolio piece: layout first, one test table, buttons and a description ([#48](https://github.com/anlit75/c4o-core/issues/48)) ([8628c76](https://github.com/anlit75/c4o-core/commit/8628c763b5a2452d78e47cbb9f5e5937238a5de5))

## [2.13.2](https://github.com/anlit75/c4o-core/compare/v2.13.1...v2.13.2) (2026-10-01)


### Fixes

* the results page says when it was built, and Timing met reads hold as well as setup ([#47](https://github.com/anlit75/c4o-core/issues/47)) ([ee6b55c](https://github.com/anlit75/c4o-core/commit/ee6b55cfd39a5ce836f3cb6df38e00b5f39af91a))

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
