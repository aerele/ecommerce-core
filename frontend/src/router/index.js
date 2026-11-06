import { createRouter, createWebHistory } from "vue-router"

// The production build is served by Frappe at /ecommerce-core (www page +
// website_route_rules catch-all). The dev server runs at the root, so the
// history base stays "/" there.
const base = import.meta.env.DEV ? "/" : "/ecommerce-core/"

export const router = createRouter({
  history: createWebHistory(base),
  routes: [
    {
      path: "/",
      redirect: { name: "ProductSync" },
    },
    {
      path: "/product-sync",
      name: "ProductSync",
      component: () => import("@/pages/ProductSync.vue"),
    },
  ],
})
