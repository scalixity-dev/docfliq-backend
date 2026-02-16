variable "env_name" {
  type = string
}

variable "cluster_name" {
  type    = string
  default = "docfliq"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "task_cpu" {
  type    = number
  default = 256
}

variable "task_memory" {
  type    = number
  default = 512
}

variable "container_image" {
  type = string
}

variable "service_name" {
  type = string
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "target_group_arn" {
  type = string
}

variable "container_port" {
  type    = number
  default = 8000
}
