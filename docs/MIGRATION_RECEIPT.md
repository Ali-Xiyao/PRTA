# PRTA-CXR migration receipt

## Authority

- Legacy source commit: `44620a345e42d1febaf38d3dda42f0e5c7449226`.
- Execution manual SHA-256:
  `9372745f26f109321995353e0417ae61bddfe893da253161c27387b21013c65f`.
- Experiment-plan SHA-256:
  `4bc372bd08e3d91d06204e00d9511aba9af23f469178eda867090b7290c42b23`.
- Clean repository commit: the commit containing this receipt (use
  `git rev-parse HEAD` so the receipt does not create a self-referential hash).

## Migration classification

`WHITELIST_REFACTOR_WITHOUT_FORMAL_EXECUTION`

- The validated mathematical core was copied before being renamed/refactored.
- New sample, Luna, manifest, leakage, native-head, receipt, and authorization
  contracts were added from the supplied manual.
- No old experiment result, patient roster, prediction, checkpoint, cache,
  protected outcome, or cloud remote was copied.
- No formal experiment, Luna API call, real-data cache, or parity run occurred.

## Document integrity

The two copies under `docs/` have the same SHA-256 values as the supplied
root documents above.
