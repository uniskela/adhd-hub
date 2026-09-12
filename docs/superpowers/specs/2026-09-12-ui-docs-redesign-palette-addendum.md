# UI/docs redesign palette addendum

Date: 2026-09-12
Branch: `feat/ui-docs-redesign`
Status: Approved
Parent spec: `docs/superpowers/specs/2026-09-12-ui-docs-redesign-design.md`

## Decision

Use **GitHub/Cursor-style darkness and restraint while preserving the Progress Hub forest/teal identity**.

This is not a switch to GitHub blue-grey and not a literal Cursor clone. The goal is developer-tool restraint: near-black neutral canvas, flat surfaces, thin low-contrast borders, little colour until something is actionable/selected, almost no decorative glow/gradient, and Progress Hub teal/gold retained as recognisable brand accents.

System remains the product default. Dark mode is the preferred showcase theme for README/docs screenshots when a single theme is needed.

## Dark palette

| Role | Value | Use |
| --- | --- | --- |
| Canvas | `#0D1210` | App/docs page background |
| Header / navigation | `#101613` | Primary chrome and side navigation |
| Primary surface | `#151D19` | Grouped content / intentional surfaces |
| Elevated surface | `#1B2520` | Dialogs, popovers, selected detail where elevation matters |
| Border / divider | `#2A3731` | Thin boundaries and separators |
| Main text | `#E7EEEA` | Headings and body |
| Muted text | `#98A89F` | Metadata and secondary copy |
| Brand accent | `#7ACDB6` | Primary action, focus, selection |
| Strong teal | `#2B8877` | Stronger brand/action treatment where needed |
| Selected subtle background | `#172A24` | Selected rows/tabs without a bright card |
| Gold accent | `#DDBB68` | Milestones/achievement emphasis only |
| Danger | `#F08C99` | Destructive actions and error emphasis |

### Dark-mode rules

- Teal identifies action, selection, focus, or meaningful state; it is not general decoration.
- Gold is reserved for milestones/achievement emphasis and should remain sparse.
- Do not use mint/teal glows around normal containers.
- Normal page regions are flat; use divider/border contrast before surface contrast, and surface contrast before shadow.
- Shadows are primarily for dialogs/popovers/true elevation.
- Do not introduce decorative radial/linear page gradients or backdrop blur.

## Light palette

Keep the warmer Progress Hub identity rather than copying GitHub white/grey exactly.

| Role | Value | Use |
| --- | --- | --- |
| Canvas | `#F7F6F1` | App/docs page background |
| Primary surface | `#FFFFFF` | Intentional grouped/elevated content |
| Secondary surface | `#EFF1EC` | Quiet grouped content / selected subtle background |
| Main text | `#20332C` | Headings and body |
| Muted text | `#617069` | Metadata and secondary copy |
| Brand teal | `#176B60` | Primary action, selection and links |
| Border / divider | `#D7DDD8` | Thin boundaries |
| Gold accent | `#B18430` | Milestones/achievement emphasis where contrast permits |
| Danger | `#AB3546` | Destructive actions/errors |

## Cross-surface requirement

`/ui` and the Zensical documentation must derive from the same semantic colour roles even if the implementation variable names differ. Avoid independent, slightly different teal/forest palettes that make the docs feel like a different product.

The palette must meet WCAG AA for ordinary body text and interactive states in both themes. Keyboard focus remains visible and should use the brand accent plus shape/outline—not colour alone.
