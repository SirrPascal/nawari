# Metric and evidence routing register

Status: policy prepared; Parent/Mimir routes require server validation.

| Family | Current laptop evidence | Proposed central route | History claim now |
| --- | --- | --- | --- |
| CPU, memory, swap, load | Netdata time series | Parent retained history; selected fleet aggregates to Mimir after sizing | Local Agent history only |
| Disk capacity and activity | Netdata time series | Parent; capacity/health subset to Mimir | Local Agent history only |
| Battery, thermal, sensors | Hardware-dependent Netdata contexts | Parent when collected; no invented series | Availability varies by hardware |
| Interface and TCP/IP statistics | Netdata time series | Parent and selected Mimir export | Local Agent history only |
| Application resource groups | `apps.plugin` aggregate time series | Parent; bounded approved groups to Mimir | Local Agent history only |
| Application connections | `topology:network-connections` Function | Bounded live Function through authorized backend only | Registered locally but access denied 412; no evidence available |
| Nawari service phases/results | `nawari.plugin` metrics plus structured evidence | Parent/Mimir metrics; PostgreSQL structured evidence | Local fixture history and intake verified |
| Network context and path | Expiring structured records | PostgreSQL investigation store | Seven-day evidence contract; central runtime pending |
| Selected operational events | Allowlisted structured records | Alloy/Loki after redaction and expiry validation | Pipeline not deployed |

Every catalogue dimension remains searchable even when its central route is `Parent only`, `live Function`, `historical`, or `unsupported`. A disappeared dimension becomes historical/not observed rather than healthy.

