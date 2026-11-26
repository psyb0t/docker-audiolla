import operations from "./.content/reference/sidebar.ts";
import { guides } from "./guide-order.mjs";

export default {
  docs: guides.map((id) => id === "api"
    ? { type: "category", label: "REST API", link: { type: "doc", id }, items: operations }
    : id),
};
