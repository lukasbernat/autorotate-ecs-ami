# autorotate-ecs-ami
Recycles ami's in an ECS cluster in AWS gracefully
# use cases
You do run an ECS cluster in aws on a set of ec2 ami's which need to be recycled gracefully (production servers)
(new OS ver, updated yum packages, new source ami, new ssh keys, etc). 
# how to run
a) boto3 will read from ~.aws/config and ~.aws/credentials
b) adjust aws specific names in source
c) make sure Termination Policies = OldestInstance in your autoscaling group. I did not change it on purpose, since this should be part of conf managment (terraform, ansible, cloudformation etc)

#what it will do
it will double your autoscaling and service count temporary
