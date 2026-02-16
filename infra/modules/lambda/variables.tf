variable "env_name" {
  type = string
}

variable "function_name" {
  type = string
}

variable "handler" {
  type    = string
  default = "handler.handler"
}

variable "runtime" {
  type    = string
  default = "python3.11"
}

variable "source_dir" {
  type    = string
  default = ""
}

variable "timeout" {
  type    = number
  default = 60
}

variable "memory_size" {
  type    = number
  default = 128
}

variable "subnet_ids" {
  type    = list(string)
  default = []
}

variable "security_group_ids" {
  type    = list(string)
  default = []
}
