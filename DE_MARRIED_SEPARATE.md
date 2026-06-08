# Germany `married_separate`

This note explains what Germany `married_separate` means legally, how it differs from both `single` and `married_joint`, and why this repo does not yet support it end-to-end.

## Legal Frame

For married spouses in Germany, the relevant legal frame is:

- `§ 26 EStG`
  Choice of assessment regime for spouses.
  https://www.gesetze-im-internet.de/estg/__26.html
- `§ 26a EStG`
  `Einzelveranlagung von Ehegatten`
  https://www.gesetze-im-internet.de/estg/__26a.html
- `§ 26b EStG`
  `Zusammenveranlagung von Ehegatten`
  https://www.gesetze-im-internet.de/estg/__26b.html

Official administrative guidance:

- BMF / Einkommensteuer-Hinweise on `§ 26`
  https://esth.bundesfinanzministerium.de/esth/2024/A-Einkommensteuergesetz/III-Veranlagung-25-30/Paragraf-26/inhalt.html
- BMF / Einkommensteuer-Hinweise on `§ 26a`
  https://esth.bundesfinanzministerium.de/esth/2022/A-Einkommensteuergesetz/III-Veranlagung/Paragraf-26a/inhalt.html

## What It Is

`married_separate` in this repo means the German posture under `§ 26a EStG`:

- the spouses are married
- they do not use `Zusammenveranlagung`
- each spouse is assessed separately

This is not the same legal posture as two unrelated single taxpayers, even though part of the tax math looks similar.

## What Is Similar To Two Single Returns

In practice, the core ordinary-income math is close to two single returns:

- each spouse is taxed on their own income
- each spouse uses the single-person tariff rather than the splitting tariff
- each spouse needs their own Germany return and their own final Germany result

That is why the ordinary-law layer in this repo can already compute `married_separate` as two single-tariff assessments.

## What Is Not The Same As Two Unrelated Single Taxpayers

It is still a spousal filing regime under `§ 26a EStG`, not just "pretend they were never married."

Important consequences:

- some items are attributed based on who economically bore the cost
- spouses can jointly request a `50/50` split for certain categories under `§ 26a Abs. 2 EStG`
- the filing workflow still needs two spouse-linked Germany returns, not two unrelated standalone returns

This matters for:

- `Sonderausgaben`
- `außergewöhnliche Belastungen`
- tax reductions under `§§ 35a` and `35c EStG`

So the implementation surface is more than "run the single-person code twice."

## Why The Repo Blocks It Today

The current repo supports Germany:

- `single`
- `married_joint`

For `married_separate`, the repo intentionally fails loudly once the pipeline would otherwise create:

- one combined capital model
- one combined forms package
- one combined ELSTER entry sheet
- one combined final Germany result

That would be misleading and legally wrong, because `married_separate` requires two separate German filing packages and two separate outcomes.

So the current boundary is:

- ordinary-law layer: partially implemented
- end-to-end capital/forms/output surface: not implemented yet

## What A Correct End-To-End Implementation Still Needs

To support Germany `married_separate` properly, the repo needs at least:

- separate capital computations per spouse where legally required
- separate Germany form packages per spouse
- separate ELSTER entry sheets per spouse
- separate audit/legal-output surfaces per spouse
- explicit handling of `§ 26a Abs. 2 EStG` allocation choices

Until that exists, failing loudly is safer than producing a plausible but wrong combined package.

## Contribution Boundary

This is a real feature gap, not a hidden one.

PRs are welcome to bridge it.

The standard for accepting that work should be:

- legally grounded against `§ 26`, `§ 26a`, and related guidance
- two distinct German filing outputs, not one household-level combined result
- tests for both the ordinary-law path and the filing/output surfaces

For the broader support picture, also see:

- [README.md](README.md)
- [docs/support-matrix.md](docs/support-matrix.md)
