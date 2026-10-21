import type { NextConfig } from "next";
import { trustedAuthOrigins } from "./lib/auth-origins";
const config: NextConfig = {
  poweredByHeader: false,
  allowedDevOrigins: trustedAuthOrigins().map(origin => new URL(origin).hostname),
};
export default config;
