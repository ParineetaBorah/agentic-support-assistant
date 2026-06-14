import axios from "axios";
import { API_BASE_URL } from "./client";
import type { User } from "../types";

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  username: string;
  role: string;
}

interface LoginResult {
  accessToken: string;
  user: User;
}

export async function getToken(username: string, password: string): Promise<LoginResult> {
  const response = await axios.post<LoginResponse>(`${API_BASE_URL}/auth/login`, { username, password });

  return {
    accessToken: response.data.access_token,
    user: {
      username: response.data.username,
      role: response.data.role,
    },
  };
}
