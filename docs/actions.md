# The actions

A repository made from the [ChipForAll](https://github.com/anlit75/ChipForAll) template has no git history in common with it. A later fix to the template's workflow does not reach that repository. The actions in `actions/` hold the steps that all such repositories share. A workflow calls them, and a fix to an action reaches each caller without a pull request.

## What a caller's job looks like

```yaml
  full-flow:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # the upload action attaches the GDS to a release on a v* tag
      pages: read       # the report action asks whether Pages is on
    outputs:
      publish-pages: ${{ steps.report.outputs.publish-pages }}
    steps:
      - uses: actions/checkout@v5
      - uses: anlit75/c4o-core/actions/setup@v2
      - uses: anlit75/c4o-core/actions/checks@v2
      # your own steps can go here, and between any two actions
      - uses: anlit75/c4o-core/actions/gds@v2
      - id: report
        uses: anlit75/c4o-core/actions/report@v2
      - if: always()
        uses: anlit75/c4o-core/actions/upload@v2
```

The actions are steps in your job. They use your workspace, so a step of your own reads `runs/` and `build/` directly.

| Action | What it does |
|---|---|
| `setup` | Starts the LibreLane image pull in the background. Checks that the Makefile and `devcontainer.json` name the same c4o-core image. Pulls that image. Restores the Sky130 PDK from the cache. Checks that the Dev Container user exists in the image. |
| `checks` | `make lint`, `make sim`, `make cocotb` when `config.yaml` has `"//COCOTB_TESTS"`, `make synth`, `make schematic`. Keeps the cocotb output in `build/cocotb-rtl.log`. |
| `gds` | Waits for the LibreLane image. `make gds`. Fails if there is no GDS in `build/` or no layout render in `runs/`. |
| `report` | `make gatesim` when `config.yaml` has `"//GATE_TESTS"`, but not on a pull request. Puts the signoff numbers on the run summary. `make site`, and checks the sections of the page. On a push to `main` with Pages set to GitHub Actions, uploads the page for a deploy job. |
| `upload` | Uploads the schematic, the layout render, and `build/` with `runs/`. On a `v*` tag, attaches the GDS to the release. Call it with `if: always()`. |

## What the actions need from your repository

- A `Makefile` with `C4O_IMAGE :=` and `LIBRELANE_IMAGE :=`, and the targets the template's Makefile has. The actions read the image names from the Makefile and call `make`. Your Makefile decides the image version, not the action.
- `config.yaml` at the top of the repository.
- The `permissions` in the example. An action cannot give itself a permission.
- A deploy job of your own for GitHub Pages. It needs `pages: write`, `id-token: write` and the `github-pages` environment, and an action cannot have them.

## Inputs and outputs

| Action | Name | Meaning |
|---|---|---|
| `setup` | output `image` | The c4o-core image that the Makefile names. |
| `setup` | output `pdk-version` | The PDK version that the image installs. |
| `setup` | output `cache-hit` | `true` when the PDK came from the cache. |
| `report` | input `sections` | More `<h2>` sections that the results page must have, one on each line. |
| `report` | input `gatesim-minutes` | The gate-level simulation stops after this time. Default: 15. |
| `report` | output `publish-pages` | `true` when the page was uploaded for a deploy. |
| `upload` | input `name` | The name of the artifact with `build/` and `runs/`. |
| `upload` | input `retention-days` | Default: 5. |

## Which version you get

`@v2` is a branch. Each release of c4o-core 2.x moves it forward to that release. Thus a caller on `@v2` gets each fix and each new step of 2.x.

A change to an action changes the CI of each caller at the same time. If you do not want that, use a release tag, for example `@v2.16.0`. You then get no fix until you change the tag.

The actions and the image have different versions in a caller. The action version is the ref after `@`. The image version is in your Makefile. A 2.x action is written to work with a 2.x image. If one does not, that is a bug in the action.
