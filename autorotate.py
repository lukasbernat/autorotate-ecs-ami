#!/usr/bin/python3
#simple app to rotate an ami gracefully in an ECS cluster without impacting the live service.  
#1 task per 1 ec2 instance considered in a given ecs service
#this was tested in a scenario where 1 ecs cluster/service is running on 1 set of autoscaling nodes
#lukasbernatca@gmail.com

import boto3, time, sys
from collections import Counter

asg_client = boto3.client('autoscaling')
ecs_client = boto3.client('ecs')
alb_client = boto3.client('elbv2')

#MODIFY THIS
asg = "EC2ContainerService-lukas-EcsInstanceAsg-1JLW41CT79MRQ"
ecs_cluster = "lukas"
ecs_service = "nginx"
alb_target_group = 'web1'
arn = 'arn:aws:elasticloadbalancing:us-west-2:243781951606:targetgroup/web1/a7c836ade61db556'


#sanity checks
def run_eq_des():
	ecs_response = ecs_client.describe_services(
		cluster=ecs_cluster,
		services=[
			ecs_service,
		]
	)
	for i in ecs_response['services']:
		ecs_current_desired = i['desiredCount']
		ecs_current_running = i['runningCount']
	if ecs_current_desired == ecs_current_running:
		return True
	else:
		return False
		
rn = run_eq_des()
print(rn)
if not rn:
	print('desired and running counts of ecs service', ecs_service, 'do not match')
	sys.exit(1)



#build a list of current instance_ids, desired and max of asg
asg_response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])
initial_ids = []
for i in asg_response['AutoScalingGroups']:
	for k in i['Instances']:
		initial_ids.append(k['InstanceId'])
for i in asg_response['AutoScalingGroups']:
	orig_maxsize = i['MaxSize']
	orig_desired = i['DesiredCapacity']


#double the size of the max and desired autoscaling group
new_maxsize = orig_maxsize*2
new_desired = orig_desired*2
double_size = asg_client.update_auto_scaling_group(
    AutoScalingGroupName=asg,
    MaxSize=new_maxsize,
    DesiredCapacity=new_desired,
)

#count autoscaling nodes currently 'InService'
def count_inservice():
	life_cycle = []
	asg_response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])
	for i in asg_response['AutoScalingGroups']:
		for k in i['Instances']:
			life_cycle.append(k['LifecycleState'])
	ct= Counter(life_cycle)
	n = ct['InService']
	return(n)
	
	
#waiting on asg to double
x = count_inservice()
while x < new_desired:
	x = count_inservice()
	print(asg, 'nodes InService equals', x, 'waiting for it to reach', new_desired)
	time.sleep(5)

#doubling ecs desired count
ecs_response = ecs_client.describe_services(
		cluster=ecs_cluster,
		services=[
			ecs_service,
		]
	)
for i in ecs_response['services']:
	ecs_current_desired = i['desiredCount']
	ecs_current_running = i['runningCount']
print('increasing ecs desired count from', ecs_current_desired, 'to', ecs_current_desired*2)
ecs_update_response = ecs_client.update_service(
    cluster=ecs_cluster,
    service=ecs_service,
    desiredCount=ecs_current_desired*2
)

#making sure doubling worked
rn = run_eq_des()
while not rn:
	time.sleep(5)
	print('waiting on ecs desired', ecs_current_desired, 'and running tasks to match', ecs_current_desired*2)
	rn = run_eq_des()

#set minimum healthy to 50%
ecs_update_response = ecs_client.update_service(
    cluster=ecs_cluster,
    service=ecs_service,
    deploymentConfiguration={
        'minimumHealthyPercent': 50
    }
)

#giving some time to register new targets, #TODO: count registered targets before proceeding
time.sleep(45)

print('decreasing ecs desired count from', ecs_current_desired*2, 'to', ecs_current_desired)
ecs_update_response = ecs_client.update_service(
    cluster=ecs_cluster,
    service=ecs_service,
    desiredCount=int(ecs_current_desired)
)

#drain old instances
for i in initial_ids:
	response = alb_client.deregister_targets(
    TargetGroupArn=arn,
    Targets=[
        {
            'Id': i,
        },
    ]
	)
	print('killing old instances \n', i,'\n', response)

#set this to alb timeout + 10, important: sleep for the amount your target group drain timeout is set #TODO fetch from current settings
time.sleep(310)

#halfing asg size
print('reverting asg size, maxsize to', orig_maxsize, 'desired', orig_desired)
double_size = asg_client.update_auto_scaling_group(
    AutoScalingGroupName=asg,
    MaxSize=orig_maxsize,
    DesiredCapacity=orig_desired,
)


#set minimum healthy to 100%
ecs_update_response = ecs_client.update_service(
    cluster=ecs_cluster,
    service=ecs_service,
    deploymentConfiguration={
        'minimumHealthyPercent': 100
    }
)
