[identifier] dense=Y keyword=Y ids=['CrashLoopBackOff']  What does CrashLoopBackOff mean?
[identifier] dense=Y keyword=Y ids=['spec.containers[].resources.limits']  How do I set spec.containers[].resources.limits for memory?
[flag      ] dense=- keyword=- ids=['--dry-run=client']  kubectl apply --dry-run=client example
[identifier] dense=Y keyword=Y ids=['PodDisruptionBudget']  What is a PodDisruptionBudget?
[prose     ] dense=Y keyword=Y ids=[]  How do I configure a liveness probe?
[identifier] dense=Y keyword=- ids=['ImagePullBackOff']  Why is my pod stuck in ImagePullBackOff?
[identifier] dense=Y keyword=Y ids=['stabilizationWindowSeconds']  How does stabilizationWindowSeconds affect scale-down?
[flag      ] dense=Y keyword=Y ids=['--ignore-daemonsets']  kubectl drain --ignore-daemonsets before node maintenance
[prose     ] dense=Y keyword=Y ids=[]  How do I spread my pods evenly across zones?
[prose     ] dense=Y keyword=- ids=[]  How do I keep a volume's data after its claim is deleted?
[identifier] dense=Y keyword=Y ids=['ttlSecondsAfterFinished']  What does ttlSecondsAfterFinished do?
[identifier] dense=- keyword=- ids=['podManagementPolicy']  What is podManagementPolicy used for?
[identifier] dense=Y keyword=Y ids=['PriorityClass']  How do I create a PriorityClass?
[identifier] dense=Y keyword=Y ids=['backoffLimit']  How does backoffLimit work?
[identifier] dense=Y keyword=Y ids=['concurrencyPolicy']  What does concurrencyPolicy: Forbid do?
[flag      ] dense=Y keyword=Y ids=['pod/mypod', '8080:80']  kubectl port-forward pod/mypod 8080:80
[flag      ] dense=Y keyword=Y ids=['--image=busybox', '--target=app']  kubectl debug -it --image=busybox --target=app
[prose     ] dense=Y keyword=Y ids=[]  How do I roll back to an earlier version of my app?
[prose     ] dense=- keyword=- ids=[]  How can I keep pods off a node unless they explicitly allow it?
[prose     ] dense=Y keyword=Y ids=[]  How do I restrict which pods can talk to each other?

dense top-10: 17/20   keyword top-10: 15/20
keyword by kind: identifier 8/10, flag 3/4, prose 4/6
dense latency   p50=187 ms p95=390 ms
keyword latency p50=210 ms p95=315 ms