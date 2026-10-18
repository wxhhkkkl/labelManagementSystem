/** 产品接口（contracts/admin-api.md 产品小节）。 */

import { request } from './client'

export interface ProductStats {
  imported: number
  allocated: number
  printed: number
}

export interface Product {
  id: number
  code: string
  name: string
  spec: string | null
  default_template_id: number | null
  status: 'active' | 'disabled'
  stats: ProductStats
}

export const listProducts = (keyword?: string) =>
  request<Product[]>(`/api/v1/products${keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''}`)

export type ProductOption = Pick<Product, 'id' | 'code' | 'name' | 'status'>
export const listProductOptions = () => request<ProductOption[]>('/api/v1/products/options')

export const createProduct = (json: Record<string, unknown>) =>
  request<Product>('/api/v1/products', { method: 'POST', json })

export const updateProduct = (id: number, json: Record<string, unknown>) =>
  request<Product>(`/api/v1/products/${id}`, { method: 'PUT', json })

export const disableProduct = (id: number) =>
  request<Product>(`/api/v1/products/${id}/disable`, { method: 'POST' })
