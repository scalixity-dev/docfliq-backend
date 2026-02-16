data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]
  filter { name = "name"; values = ["amzn2-ami-hvm-*-x86_64-gp2"] }
}

resource "aws_instance" "main" {
  count         = var.key_name != "" ? 1 : 0
  ami           = data.aws_ami.amazon_linux_2.id
  instance_type = var.instance_type
  subnet_id     = var.subnet_id
  key_name      = var.key_name
  tags = { Name = "docfliq-${var.env_name}-ec2", Env = var.env_name }
}
