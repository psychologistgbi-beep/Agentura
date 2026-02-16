# SUPPORT INCIDENT REPORT TEMPLATE

Use this template when Technical Lead reports incident handling outcome back to EA.

```text
SUPPORT INCIDENT REPORT
Incident ID: <ID>
Date: <YYYY-MM-DD>
Owner: <Technical Lead>
Status: <resolved|partially_resolved|rework_required>

1) Business impact
- <what business result was blocked>

2) Root cause
- <primary root cause>
- <secondary contributing factors>

3) Corrective actions
- <action 1>
- <action 2>

4) Verification evidence
- Commands:
  - <command>
  - <command>
- Results:
  - <result summary>

5) Agents involved (mandatory)
- <agent role/name>
- <agent role/name>

6) Parallel execution metrics (mandatory)
- configured parallel lanes: <N>
- observed max parallel lanes: <N>

7) Residual risks
- <risk>

8) EA retry instruction
- retry command(s):
  - <command>
  - <command>
- expected business result:
  - <expected outcome>

9) Remediation verdict (mandatory)
- root-cause elimination confirmed: <YES|NO>
- EA retry authorized now: <YES|NO>
- notes: <short rationale>
```
