import useSWRinternal from "swr";

const fetcher = (...args) => fetch(...args).then((res) => res.json());

export function useSWR(path: string) {
    return useSWRinternal(path, fetcher)
}