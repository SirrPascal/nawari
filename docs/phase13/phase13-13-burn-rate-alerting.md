# Phase 13.13 — Multi-Window Multi-Burn-Rate Alerting Architecture

## Alerting Philosophy

Traditional threshold alerting fires when a single metric exceeds a static limit, often resulting in false positives during brief spikes or delayed pages during slow, catastrophic budget leaks.

In Phase 13.13, Nawari implements the **Google SRE Multi-Window Multi-Burn-Rate** alerting standard. Alert severity is determined by how fast the 30-day error budget is being consumed, ensuring fast detection for severe outages and noise-free handling of minor transient fluctuations.

---

## 1. Multi-Window Alerting Matrix

| Alert Level | Window Size | Minimum Burn Rate | Budget Consumed in Window | Time to Exhaustion (TTX) | Target Action | Recipient Notification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CRITICAL_PAGE** | **1 Hour** | **14.4x** | $\ge 2.0\%$ | $\le 50\text{ hours}$ ($\approx 2\text{ days}$) | **Action 10 / 12** | Pager / SMS / Email to On-Call Specialists & Duty Manager |
| **WARNING_TICKET** | **6 Hours** | **6.0x** | $\ge 5.0\%$ | $\le 120\text{ hours}$ ($\approx 5\text{ days}$) | **Action 13** | Automated JIRA / ServiceNow Incident Ticket |
| **LONG_WARNING** | **24 Hours** | **3.0x** | $\ge 10.0\%$ | $\le 240\text{ hours}$ ($\approx 10\text{ days}$) | **Action 13** | Daily Operational Briefing / Standup Ticket |
| **NOMINAL** | 30 Days | $< 1.0\text{x}$ | $< 100.0\%$ | $> 720\text{ hours}$ | *None* | Silent operation |

---

## 2. Multi-Window Alerting Logic

To eliminate reset oscillations and false pages, both short and long windows must agree:
- **Critical Page Condition**:
  $$\text{Burn Rate}_{1h} \ge 14.4 \quad \text{AND} \quad \text{Burn Rate}_{5m} \ge 14.4$$
- **Warning Ticket Condition**:
  $$\text{Burn Rate}_{6h} \ge 6.0 \quad \text{AND} \quad \text{Burn Rate}_{30m} \ge 6.0$$

---

## 3. Mathematical Verification

For `SVC-SIP-CARRIER` (SLO $99.99\%$, monthly allowed downtime $4.32\text{ minutes}$):
- $2\%$ of error budget is $0.0864\text{ minutes}$ ($5.18\text{ seconds}$).
- A $1.0\text{-minute}$ outage in a 1-hour window yields:
  $$\text{Error Rate}_{1h} = \frac{1.0}{60.0} = 0.01667$$
  $$\text{Unreliability} = 1.0 - 0.9999 = 0.0001$$
  $$\text{Burn Rate} = \frac{0.01667}{0.0001} = 166.7x$$
- Because $166.7x \gg 14.4x$, this triggers an immediate `CRITICAL_PAGE` with an estimated time-to-exhaustion of $3.3\text{ hours}$.
