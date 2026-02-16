output "instance_id" {
  value = length(aws_instance.main) > 0 ? aws_instance.main[0].id : null
}
