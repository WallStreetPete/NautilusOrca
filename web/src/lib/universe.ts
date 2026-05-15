// Universe + dependency graph data. Mirrors src/blackorca/universe/{semis,dependency_graph}.py
// Keep in sync manually — this is small.

export type Tier = 1 | 2 | 3;

export type SemiName = {
  symbol: string;
  name: string;
  tier: Tier;
  segment: string;
  avg_adv: "low" | "mid" | "high" | "mega";
  mcap_bucket: "small" | "mid" | "large" | "mega";
  country: string;
};

export const SEMI_UNIVERSE: readonly SemiName[] = [
  { symbol: "NVDA", name: "NVIDIA", tier: 1, segment: "fabless", avg_adv: "mega", mcap_bucket: "mega", country: "US" },
  { symbol: "AMD",  name: "Advanced Micro Devices", tier: 1, segment: "fabless", avg_adv: "high", mcap_bucket: "mega", country: "US" },
  { symbol: "TSM",  name: "Taiwan Semi", tier: 1, segment: "foundry", avg_adv: "high", mcap_bucket: "mega", country: "TW" },
  { symbol: "AVGO", name: "Broadcom", tier: 1, segment: "fabless", avg_adv: "high", mcap_bucket: "mega", country: "US" },
  { symbol: "ASML", name: "ASML", tier: 1, segment: "equipment", avg_adv: "high", mcap_bucket: "mega", country: "NL" },
  { symbol: "INTC", name: "Intel", tier: 1, segment: "logic", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "QCOM", name: "Qualcomm", tier: 1, segment: "fabless", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "MU",   name: "Micron", tier: 1, segment: "memory", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "TXN",  name: "Texas Instruments", tier: 1, segment: "analog", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "AMAT", name: "Applied Materials", tier: 2, segment: "equipment", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "LRCX", name: "Lam Research", tier: 2, segment: "equipment", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "KLAC", name: "KLA", tier: 2, segment: "equipment", avg_adv: "high", mcap_bucket: "large", country: "US" },
  { symbol: "MRVL", name: "Marvell", tier: 2, segment: "fabless", avg_adv: "mid", mcap_bucket: "large", country: "US" },
  { symbol: "NXPI", name: "NXP", tier: 2, segment: "analog", avg_adv: "mid", mcap_bucket: "large", country: "US" },
  { symbol: "ON",   name: "ON Semi", tier: 2, segment: "sic", avg_adv: "mid", mcap_bucket: "mid", country: "US" },
  { symbol: "ADI",  name: "Analog Devices", tier: 2, segment: "analog", avg_adv: "mid", mcap_bucket: "large", country: "US" },
  { symbol: "STM",  name: "STMicroelectronics", tier: 2, segment: "analog", avg_adv: "mid", mcap_bucket: "mid", country: "IT" },
  { symbol: "WOLF", name: "Wolfspeed", tier: 2, segment: "sic", avg_adv: "low", mcap_bucket: "small", country: "US" },
  { symbol: "ARM",  name: "Arm Holdings", tier: 3, segment: "ip_design", avg_adv: "mid", mcap_bucket: "large", country: "GB" },
  { symbol: "MCHP", name: "Microchip", tier: 3, segment: "analog", avg_adv: "mid", mcap_bucket: "mid", country: "US" },
  { symbol: "LSCC", name: "Lattice", tier: 3, segment: "fabless", avg_adv: "low", mcap_bucket: "small", country: "US" },
  { symbol: "AEHR", name: "Aehr Test", tier: 3, segment: "test_packaging", avg_adv: "low", mcap_bucket: "small", country: "US" },
  { symbol: "UCTT", name: "Ultra Clean Holdings", tier: 3, segment: "equipment", avg_adv: "low", mcap_bucket: "small", country: "US" },
  { symbol: "IVAC", name: "Intevac", tier: 3, segment: "equipment", avg_adv: "low", mcap_bucket: "small", country: "US" },
  { symbol: "ENTG", name: "Entegris", tier: 3, segment: "equipment", avg_adv: "mid", mcap_bucket: "mid", country: "US" },
  { symbol: "ACMR", name: "ACM Research", tier: 3, segment: "equipment", avg_adv: "low", mcap_bucket: "small", country: "US" },
];

export type SupplierEdge = {
  upstream: string;
  downstream: string;
  relationship: string;
  expected_lag_days: number;
  confidence: number;
};

export const DEPENDENCY_GRAPH: readonly SupplierEdge[] = [
  { upstream: "NVDA", downstream: "TSM",  relationship: "TSMC is NVDA's sole high-end foundry", expected_lag_days: 3, confidence: 0.85 },
  { upstream: "NVDA", downstream: "AMAT", relationship: "Advanced packaging tools — NVDA AI capex pull-through", expected_lag_days: 5, confidence: 0.55 },
  { upstream: "NVDA", downstream: "LRCX", relationship: "Etch tools for HBM stacks", expected_lag_days: 5, confidence: 0.55 },
  { upstream: "NVDA", downstream: "ENTG", relationship: "Materials & purity in HBM / CoWoS", expected_lag_days: 7, confidence: 0.45 },
  { upstream: "NVDA", downstream: "MU",   relationship: "HBM3/HBM3e shipped into NVDA accelerators", expected_lag_days: 3, confidence: 0.60 },
  { upstream: "NVDA", downstream: "AVGO", relationship: "AI networking ASICs adjacent to NVDA platforms", expected_lag_days: 5, confidence: 0.40 },
  { upstream: "TSM",  downstream: "ASML", relationship: "Lithography — TSM is ASML's biggest customer", expected_lag_days: 5, confidence: 0.70 },
  { upstream: "TSM",  downstream: "KLAC", relationship: "Process control / yield — ramps with TSM", expected_lag_days: 5, confidence: 0.55 },
  { upstream: "TSM",  downstream: "AMAT", relationship: "Deposition / packaging tools", expected_lag_days: 5, confidence: 0.50 },
  { upstream: "TSM",  downstream: "ENTG", relationship: "Specialty materials & filtration", expected_lag_days: 7, confidence: 0.40 },
  { upstream: "TSM",  downstream: "ACMR", relationship: "Cleaning equipment — leveraged to TSM capex", expected_lag_days: 7, confidence: 0.35 },
  { upstream: "AMD",  downstream: "MRVL", relationship: "Both leveraged to AI datacenter capex", expected_lag_days: 3, confidence: 0.45 },
  { upstream: "AMD",  downstream: "AVGO", relationship: "Co-shipped in datacenter / networking stacks", expected_lag_days: 5, confidence: 0.40 },
  { upstream: "QCOM", downstream: "ARM",  relationship: "Royalty exposure to QCOM volumes", expected_lag_days: 3, confidence: 0.50 },
  { upstream: "ON",   downstream: "WOLF", relationship: "Both SiC EV plays; correlated on auto-cycle news", expected_lag_days: 2, confidence: 0.55 },
  { upstream: "STM",  downstream: "WOLF", relationship: "STM signed long-term SiC supply with WOLF", expected_lag_days: 3, confidence: 0.40 },
  { upstream: "AMAT", downstream: "UCTT", relationship: "UCTT supplies subsystems to AMAT", expected_lag_days: 7, confidence: 0.60 },
  { upstream: "LRCX", downstream: "UCTT", relationship: "UCTT supplies subsystems to LRCX", expected_lag_days: 7, confidence: 0.60 },
  { upstream: "AMAT", downstream: "IVAC", relationship: "Niche capex pull-through", expected_lag_days: 10, confidence: 0.30 },
];
