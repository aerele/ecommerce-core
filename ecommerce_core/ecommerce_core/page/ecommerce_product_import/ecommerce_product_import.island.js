// Desk loads this module and calls mount() to draw the page.
import { mountVueIsland } from "@framework/ui/island";

import Page from "./ecommerce_product_import.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
