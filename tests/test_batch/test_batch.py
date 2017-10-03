from __future__ import unicode_literals

import boto3
from botocore.exceptions import ClientError
import sure  # noqa
from moto import mock_batch, mock_iam, mock_ec2, mock_ecs


DEFAULT_REGION = 'eu-central-1'


def _get_clients():
    return boto3.client('ec2', region_name=DEFAULT_REGION), \
           boto3.client('iam', region_name=DEFAULT_REGION), \
           boto3.client('ecs', region_name=DEFAULT_REGION), \
           boto3.client('batch', region_name=DEFAULT_REGION)


def _setup(ec2_client, iam_client):
    """
    Do prerequisite setup
    :return: VPC ID, Subnet ID, Security group ID, IAM Role ARN
    :rtype: tuple
    """
    resp = ec2_client.create_vpc(CidrBlock='172.30.0.0/24')
    vpc_id = resp['Vpc']['VpcId']
    resp = ec2_client.create_subnet(
        AvailabilityZone='eu-central-1a',
        CidrBlock='172.30.0.0/25',
        VpcId=vpc_id
    )
    subnet_id = resp['Subnet']['SubnetId']
    resp = ec2_client.create_security_group(
        Description='test_sg_desc',
        GroupName='test_sg',
        VpcId=vpc_id
    )
    sg_id = resp['GroupId']

    resp = iam_client.create_role(
        RoleName='TestRole',
        AssumeRolePolicyDocument='some_policy'
    )
    iam_arn = resp['Role']['Arn']

    return vpc_id, subnet_id, sg_id, iam_arn


# Yes, yes it talks to all the things
@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_create_managed_compute_environment():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    resp = batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='MANAGED',
        state='ENABLED',
        computeResources={
            'type': 'EC2',
            'minvCpus': 5,
            'maxvCpus': 10,
            'desiredvCpus': 5,
            'instanceTypes': [
                't2.small',
                't2.medium'
            ],
            'imageId': 'some_image_id',
            'subnets': [
                subnet_id,
            ],
            'securityGroupIds': [
                sg_id,
            ],
            'ec2KeyPair': 'string',
            'instanceRole': iam_arn,
            'tags': {
                'string': 'string'
            },
            'bidPercentage': 123,
            'spotIamFleetRole': 'string'
        },
        serviceRole=iam_arn
    )
    resp.should.contain('computeEnvironmentArn')
    resp['computeEnvironmentName'].should.equal(compute_name)

    # Given a t2.medium is 2 vcpu and t2.small is 1, therefore 2 mediums and 1 small should be created
    resp = ec2_client.describe_instances()
    resp.should.contain('Reservations')
    len(resp['Reservations']).should.equal(3)

    # Should have created 1 ECS cluster
    resp = ecs_client.list_clusters()
    resp.should.contain('clusterArns')
    len(resp['clusterArns']).should.equal(1)


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_create_unmanaged_compute_environment():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    resp = batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )
    resp.should.contain('computeEnvironmentArn')
    resp['computeEnvironmentName'].should.equal(compute_name)

    # Its unmanaged so no instances should be created
    resp = ec2_client.describe_instances()
    resp.should.contain('Reservations')
    len(resp['Reservations']).should.equal(0)

    # Should have created 1 ECS cluster
    resp = ecs_client.list_clusters()
    resp.should.contain('clusterArns')
    len(resp['clusterArns']).should.equal(1)

# TODO create 1000s of tests to test complex option combinations of create environment


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_describe_compute_environment():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )

    resp = batch_client.describe_compute_environments()
    len(resp['computeEnvironments']).should.equal(1)
    resp['computeEnvironments'][0]['computeEnvironmentName'].should.equal(compute_name)

    # Test filtering
    resp = batch_client.describe_compute_environments(
        computeEnvironments=['test1']
    )
    len(resp['computeEnvironments']).should.equal(0)


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_delete_unmanaged_compute_environment():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )

    batch_client.delete_compute_environment(
        computeEnvironment=compute_name,
    )

    resp = batch_client.describe_compute_environments()
    len(resp['computeEnvironments']).should.equal(0)

    resp = ecs_client.list_clusters()
    len(resp.get('clusterArns', [])).should.equal(0)


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_delete_managed_compute_environment():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='MANAGED',
        state='ENABLED',
        computeResources={
            'type': 'EC2',
            'minvCpus': 5,
            'maxvCpus': 10,
            'desiredvCpus': 5,
            'instanceTypes': [
                't2.small',
                't2.medium'
            ],
            'imageId': 'some_image_id',
            'subnets': [
                subnet_id,
            ],
            'securityGroupIds': [
                sg_id,
            ],
            'ec2KeyPair': 'string',
            'instanceRole': iam_arn,
            'tags': {
                'string': 'string'
            },
            'bidPercentage': 123,
            'spotIamFleetRole': 'string'
        },
        serviceRole=iam_arn
    )

    batch_client.delete_compute_environment(
        computeEnvironment=compute_name,
    )

    resp = batch_client.describe_compute_environments()
    len(resp['computeEnvironments']).should.equal(0)

    resp = ec2_client.describe_instances()
    resp.should.contain('Reservations')
    len(resp['Reservations']).should.equal(3)
    for reservation in resp['Reservations']:
        reservation['Instances'][0]['State']['Name'].should.equal('terminated')

    resp = ecs_client.list_clusters()
    len(resp.get('clusterArns', [])).should.equal(0)


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_update_unmanaged_compute_environment_state():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )

    batch_client.update_compute_environment(
        computeEnvironment=compute_name,
        state='DISABLED'
    )

    resp = batch_client.describe_compute_environments()
    len(resp['computeEnvironments']).should.equal(1)
    resp['computeEnvironments'][0]['state'].should.equal('DISABLED')


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_create_job_queue():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    resp = batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )
    arn = resp['computeEnvironmentArn']

    resp = batch_client.create_job_queue(
        jobQueueName='test_job_queue',
        state='ENABLED',
        priority=123,
        computeEnvironmentOrder=[
            {
                'order': 123,
                'computeEnvironment': arn
            },
        ]
    )
    resp.should.contain('jobQueueArn')
    resp.should.contain('jobQueueName')
    queue_arn = resp['jobQueueArn']

    resp = batch_client.describe_job_queues()
    resp.should.contain('jobQueues')
    resp['jobQueues'][0]['jobQueueArn'].should.equal(queue_arn)


@mock_ec2
@mock_ecs
@mock_iam
@mock_batch
def test_job_queue_bad_arn():
    ec2_client, iam_client, ecs_client, batch_client = _get_clients()
    vpc_id, subnet_id, sg_id, iam_arn = _setup(ec2_client, iam_client)

    compute_name = 'test_compute_env'
    resp = batch_client.create_compute_environment(
        computeEnvironmentName=compute_name,
        type='UNMANAGED',
        state='ENABLED',
        serviceRole=iam_arn
    )
    arn = resp['computeEnvironmentArn']

    try:
        batch_client.create_job_queue(
            jobQueueName='test_job_queue',
            state='ENABLED',
            priority=123,
            computeEnvironmentOrder=[
                {
                    'order': 123,
                    'computeEnvironment': arn + 'LALALA'
                },
            ]
        )
    except ClientError as err:
        err.response['Error']['Code'].should.equal('ClientException')
