# Merino Developer Guidelines and Social Contract
This is an additional contractual document on top of [CONTRIBUTING](../CONTRIBUTING.md).
## Foster a Shared Ownership

Not only do Merino developers build the service together, they also share the ownership of the service. That ownership is embodied in the following responsibilities:

- Be responsible for the entire lifecycle of each change landed in the code base: from writing the PR and getting it merged; ensuring it goes through CI/CD and eventually deployed to production; setting up monitoring on metrics and ensuring its healthy status and the overall health of Merino.
- Be familiar with Merino’s operation. Conduct operational reviews on a regular basis. Identify and track operational issues. Coordinate with the team(s) to close action items and resolve the identified issues.
- Documentation. Make sure the code meets the documentation requirements (no linting errors). If a change adds/updates the API, logs or metrics, ensure the associated documentation is up to date.

We commit to sharing knowledge about Merino across the team, with the long-term goal that each team member is capable of resolving incidents of Merino. Merino developers should familiarize themselves with the Mozilla Incident Response Process and the Merino Runbooks. Each individual should be able to initiate an incident response, serve as the incident handling manager, and drive it to its resolution along with other incident responders. Any issues associated with an incident should be tracked in Jira in a way the team agrees upon. For example, assigned with an ‘incident-action-items’ label.

- Be aware of the infrastructure costs associated with new functionality. The team should have a good understanding of the cost to run the service including logging, computing, networking, and storage costs.
- Be mindful of work hours and the time zones of your fellow developers when scheduling meetings, deploying code, pairing on code, or collaborating in other ways. Set your work hours in Google Calendar and configure Slack to receive notifications only during those times. We encourage code deployments when there are fellow developers online to support. If you must deploy off-hours, ensure you have a peer available to approve any potential rollbacks.

We are not going to grow individual Merino developers in deployment, operation, documentation, and incident responding for Merino. Rather, we’d like to foster a shared ownership with shared knowledge in every aspect of the day-to-day job for Merino.

## Use ADRs to Record Architectural Decisions

ADRs (Architectural Decision Record) are widely adopted by teams at Mozilla to capture important architecture decisions, including their context and consequences. Developers are encouraged to exercise the ADR process to facilitate the decision making on important subjects of the project. ADRs should be made easy to access and reference and therefore are normally checked into the source control and rendered as part of the project documentation.

## Use SLO and Error Budget to Manage Service Risks

We strive to build highly available and reliable services while also emphasizing rapid iteration and continuous deployment as key aspects of product development. We opt to use SLOs (Service Level Objective) and error budget for risk management. SLOs can be co-determined by the product owner(s) and the service builders & operators. The error budget should be monitored and enforced by the monitoring infrastructure. Once the budget is reached, the service owners should be more reluctant or even reject to accept risky code artifacts until the budget gets reset.

## Request RRA for New Content Integrations

RRA (Rapid Risk Assessment) is the recommended process for service builders to perform a standardized lightweight risk assessment for the service or the feature of interest. Since Merino is a user-facing consumer service, we shall take extra caution for user security and the related risks. We have agreed with the Security Assurance team that we’d request an RRA (by following the RRA instructions) for every new content integration (e.g. AccuWeather) or content storage (e.g. Elasticsearch) for Merino.

## Testing for Productivity & Reliability

We value testing as a mechanism of establishing feedback loops for service development, design, and release. As developers add new changes to the project, thorough and effective testing reduces uncertainty and generates short feedback loops, accelerating development, release, and regression resolution. Testing also helps reduce the potential decrease in reliability from each change. To materialize those merits for Merino, we have designed the Merino Test Strategy and fulfilled it with adequate tests. We anticipate the cross-functional team to adhere to the strategy and evolve it to better support the project over time.

## Aim for Simplicity

We prioritize simple and conventional solutions in all aspects of development, from system design, to API specs, to code. We prefer mature, battle-tested technologies over complex, cutting-edge alternatives. At the same time, we know that Merino can always get better, and we welcome ideas from everyone. If you’ve got a new approach in mind, share it with the team or propose an Architectural Decision Record (ADR).

## Blame-free Culture

While we strive to make Merino a highly reliable service, things would still go wrong regardless of how much care we take. Code errors, misconfigurations, operational glitches, to name a few. We opt for a blame-free culture to ease the mental stress when individuals are encouraged to take on more activities & responsibilities, especially before they gain familiarity around the tasks. We believe that learning from mistakes and incorporating the learned experience into processes to avoid repeating the same mistakes is more constructive and useful than putting someone on center stage. With a blame-free culture and proper risk management processes in place, the average cost of failures should be more tolerable within the error budget boundary. Who would be afraid of making mistakes?

## Have Fun

Last but not least. Let’s make Merino a fun project to work with!